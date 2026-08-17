#!/usr/bin/env python3
"""AI 日报自动生成器 — 独立运行，不依赖 Hermes

流程：调 DeepSeek API 生成 3 份日报 → 更新网页 → git 推送
由 macOS launchd 在每天 6:00 触发。
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 统一使用北京时间（北京 = UTC+8），避免云端服务器 UTC 时区导致日期错位
BEIJING_TZ = timezone(timedelta(hours=8))

def now_beijing():
    """返回北京时间（无论服务器时区）"""
    return datetime.now(BEIJING_TZ)

ARCHIVE = Path(os.environ.get("ARCHIVE_DIR", str(Path.home() / "Desktop" / "AI日报档案")))
REPORTS = ARCHIVE / "reports"
LOG = Path(os.environ.get("REPORT_LOG", str(Path.home() / "Desktop" / "AI日报档案" / "daily_report.log")))
ENV_FILE = Path.home() / ".hermes" / ".env"
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"  # DeepSeek V3


def log(msg):
    line = f"[{now_beijing().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_api_key():
    # 云端：环境变量直接给；本地：从 .env 读取
    env_key = os.environ.get("DEEPSEEK_API_KEY")
    if env_key:
        return env_key.strip()
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            m = re.match(r"DEEPSEEK_API_KEY=(.+)", line.strip())
            if m:
                return m.group(1).strip().strip('"').strip("'")
    raise RuntimeError("DEEPSEEK_API_KEY 未找到")


def call_llm(api_key, system, user, max_retries=2):
    """调用 DeepSeek API（流式），带重试"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": True,
        "max_tokens": 6000,
        "temperature": 0.8,
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    for attempt in range(max_retries + 1):
        try:
            full = ""
            with urllib.request.urlopen(req, timeout=1500) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            full += delta
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
            if len(full.strip()) > 200:
                return full.strip()
            log(f"  内容过短({len(full)}字符)，重试 {attempt+1}")
        except Exception as e:
            log(f"  API 调用失败: {e}，重试 {attempt+1}")
            time.sleep(15)
    raise RuntimeError("API 多次调用失败")


REPORT_SPECS = [
    {
        "filename": "AI赚钱日报_详细版_%Y%m%d.md",
        "system": "你是 AI 个体赚钱案例研究专家。输出简体中文 Markdown 日报。",
        "user": """生成《AI 个体赚钱案例日报》，日期 {date}。结构：
# AI 个体赚钱案例日报 — {date_cn}
> 聚焦海外AI个体赚钱案例，每期提供国内可复制路径分析
## 一、本周海外 AI 个体赚钱案例（3-4个）
每个案例包含：**背景**、**具体做法**（分步骤）、**收入情况**、**国内可复制性**（可行性星级+具体方案）、**一句话建议**
## 二、赚钱逻辑总结（表格：模式/代表案例/核心能力/国内可行性）
## 三、本周最可执行的赚钱方向
## 四、信息来源
在文末列出本日报所有信息来源，格式：
- [来源名称1](https://真实链接)
- [来源名称2](https://真实链接)
要求：
1. 每个案例必须对应至少 1 条真实来源链接（公司官网、创始人主页、权威媒体报道，如 TechCrunch、Product Hunt 等），**禁止编造 URL**，不确定就写官方主页域名
2. 链接放在对应案例正文末尾和文末"信息来源"小节
3. 用真实存在的海外案例（如 ShipFast、Marc Lou、Pieter Levels、AI 视频工厂等），不要虚构""",
    },
    {
        "filename": "AI应用场景日报_详细版_%Y%m%d.md",
        "system": "你是 AI 企业应用落地专家。输出简体中文 Markdown 日报。",
        "user": """生成《AI 应用场景与技巧日报》，日期 {date}。结构：
# AI 应用场景与技巧日报 — {date_cn}
> 聚焦 AI 在垂直行业的真实落地案例，每期提供可复用的操作技巧
## 一、本周 AI 垂直行业落地案例（3-4个）
覆盖不同行业（财务/医疗/电商/制造/教育/法律/物流等），每个案例包含：**背景**（公司+行业）、**具体做法**、**提效数据**（量化）、**国内可复制性**
## 二、近期 AI 工具/模型重要更新（表格：工具/更新内容/对应用场景的影响）
## 三、可复用的操作技巧（2-3个，带具体 prompt 或步骤）
## 四、本周最值得试的 AI 应用方向
## 五、信息来源
在文末列出本日报所有信息来源，格式：
- [来源名称1](https://真实链接)
- [来源名称2](https://真实链接)
要求：
1. 每个案例必须对应至少 1 条真实来源链接（公司官网、官方新闻稿、权威媒体报道），**禁止编造 URL**，不确定就写官方主页域名
2. 链接放在对应案例正文末尾和文末"信息来源"小节
3. 用真实案例，不要虚构""",
    },
    {
        "filename": "AI前沿情报日报_详细版_%Y%m%d.md",
        "system": "你是 AI 行业分析师。输出简体中文 Markdown 日报。",
        "user": """生成《AI 前沿情报日报》，日期 {date}。结构：
# AI 前沿情报日报 — {date_cn}
> 聚焦 AI 产业趋势、模型动态与政策变化
## 一、今日 4-5 大 AI 趋势（每个：事件/分析/影响，约200字）
## 二、重要模型/产品更新（表格）
## 三、政策与监管动态（2-3条）
## 四、机会与风险（表格）
## 五、信息来源
在文末列出本日报所有信息来源，格式：
- [来源名称1](https://真实链接)
- [来源名称2](https://真实链接)
要求：
1. 每个趋势必须对应至少 1 条真实来源链接（公司官网、官方博客、权威媒体如 Reuters、TechCrunch），**禁止编造 URL**，不确定就写官方主页域名
2. 链接放在对应趋势正文末尾和文末"信息来源"小节
3. 基于你的训练知识写真实存在的内容，不要虚构""",
    },
    {
        "filename": "AI机会雷达_详细版_%Y%m%d.md",
        "system": "你是 AI 变现机会猎手，擅长把行业信息翻译成普通人可执行的赚钱动作。输出简体中文 Markdown。",
        "user": """生成《AI 机会雷达》，日期 {date}。这是给想用 AI 赚钱的小个体户看的执行清单，不是新闻。结构：
# AI 机会雷达 — {date_cn}
> 每天 3 个可执行的机会，看完就能动手
## 一、今日 3 大机会
每个机会用固定格式：
### 🎯 机会 N：<一句话说清机会>
- **机会说明**：这个趋势/案例里，普通人能抓住的赚钱点是什么（2-3句）
- **适合谁**：无技术背景 / 会基本电脑操作 / 懂某行业（选最贴合的一个）
- **第一步**：今天就能做的具体动作（越具体越好，如"注册XX，搭第一个demo"）
- **机会指数**：⭐×N（1-5星，综合门槛和回报）
## 二、本周行动清单
列出 3 件事，按"今天/本周/本月"排序
## 三、信息来源
- [来源名称1](https://真实链接)
要求：机会必须基于真实趋势/案例，来源链接不编造，不确定写官方主页域名""",
    },
    {
        "filename": "AI行业深潜_详细版_%Y%m%d.md",
        "days": [0],  # 每周一
        "system": "你是 AI 行业分析专家，擅长挖掘垂直行业的 AI 赚钱切入点。输出简体中文 Markdown。",
        "user": """生成《AI 行业深潜》，日期 {date}。每周深挖一个垂直行业，帮读者判断"这个行业值不值得进"。本期行业请选择：宠物、婚庆、健身、教培、医美、跨境电商、汽修、家政、餐饮、养老、房产中介、旅游 之一（选一个未深潜过的）。结构：
# AI 行业深潜 — <行业名>
> 每周深挖一个垂直行业
## 一、行业现状（市场规模/痛点/利润点，约200字）
## 二、AI 切入点（3-5个，每个：场景描述+用什么AI工具+预计投入）
## 三、赚钱案例（2-3个，真实或高度可信的，含来源链接）
## 四、行动清单（本周可做的 5 件事，按难度排序）
## 五、信息来源
- [来源名称1](https://真实链接)
要求：来源链接不编造，不确定写官方主页域名""",
    },
    {
        "filename": "AI避坑指南_详细版_%Y%m%d.md",
        "days": [2],  # 每周三
        "system": "你是 AI 行业反诈专家，专门揭露 AI 赚钱的坑和骗局。输出简体中文 Markdown。",
        "user": """生成《AI 避坑指南》，日期 {date}。帮读者识别 AI 赚钱路上的坑。结构：
# AI 避坑指南 — {date_cn}
> 每周一次，帮你躲开 AI 赚钱的坑
## 一、本期 3 大坑（每个：坑是什么/怎么骗人的/怎么识别）
## 二、失败案例复盘（1-2个真实感强的案例+教训）
## 三、防割指南（5条铁律，一眼识别韭菜课和骗局）
## 四、信息来源
- [来源名称1](https://真实链接)
要求：来源链接不编造，不确定写官方主页域名""",
    },
    {
        "filename": "AI工具箱_详细版_%Y%m%d.md",
        "days": [1, 3],  # 每周二、周四
        "system": "你是 AI 工具评测专家。输出简体中文 Markdown。",
        "user": """生成《AI 工具箱》，日期 {date}。推荐 3 个对赚钱/提效有帮助的 AI 工具。结构：
# AI 工具箱 — {date_cn}
> 每次 3 个新工具，20 秒看完
## 一、工具 1：<名称>
- **干什么用**：一句话
- **谁适合**：无技术/会电脑/懂行业
- **价格**：免费/付费/免费+付费
- **一句话点评**：值不值得用
（工具 2、工具 3 同样格式）
## 二、本周工具速查表（表格：工具/用途/价格/推荐度）
## 三、信息来源
- [来源名称1](https://真实链接)
要求：推荐真实存在的工具（如 Coze、剪映、即梦、可灵、DeepSeek、Kimi、秘塔等），来源链接不编造，不确定写官网主页""",
    },
]


def shorten_url(url, api_key=None):
    """用 tinyurl 免费 API 缩短链接，失败返回原链接"""
    url = url.strip().rstrip(')').rstrip('。').rstrip('，')
    if not url.startswith('http'):
        return url
    try:
        req = urllib.request.Request(
            f"https://tinyurl.com/api-create.php?url={urllib.parse.quote(url, safe='')}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            short = resp.read().decode('utf-8').strip()
            if short.startswith('http') and len(short) < len(url):
                return short
    except Exception:
        pass
    return url


def post_process_links(text):
    """按黄哥指示：不用短链，全部保留原链接（短链服务在国内被墙，降低稳定性）"""
    return text, 0


def git_push():
    # 云端 GitHub Actions：配置身份 + token 认证
    if os.environ.get("GITHUB_ACTIONS") == "true":
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=ARCHIVE, capture_output=True)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], cwd=ARCHIVE, capture_output=True)
        token = os.environ.get("GITHUB_TOKEN", "")
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        if token and repo:
            subprocess.run(
                ["git", "remote", "set-url", "origin", f"https://x-access-token:{token}@github.com/{repo}.git"],
                cwd=ARCHIVE, capture_output=True,
            )
    # 顺序：先 add + commit（本地提交），再 pull --rebase（合入远程），最后 push
    add = subprocess.run(["git", "add", "-A"], cwd=ARCHIVE, capture_output=True, text=True, timeout=60)
    commit = subprocess.run(["git", "commit", "-m", f"更新 {now_beijing().strftime('%Y-%m-%d')}"], cwd=ARCHIVE, capture_output=True, text=True, timeout=60)
    if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr):
        log(f"  git commit: rc={commit.returncode} {(commit.stdout+commit.stderr).strip()[:200]}")
    # pull --rebase（忽略错误：可能是首次/无远程）
    pull = subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=ARCHIVE, capture_output=True, text=True, timeout=120)
    if pull.returncode != 0:
        log(f"  git pull: rc={pull.returncode} {pull.stderr.strip()[:200]}")
    push = subprocess.run(["git", "push", "origin", "main"], cwd=ARCHIVE, capture_output=True, text=True, timeout=120)
    out = (push.stdout + push.stderr).strip()
    if push.returncode != 0 and "rejected" in out:
        log("  push 被拒绝，再 pull 一次后重试")
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=ARCHIVE, capture_output=True, text=True, timeout=120)
        r2 = subprocess.run(["git", "push", "origin", "main"], cwd=ARCHIVE, capture_output=True, text=True, timeout=120)
        out2 = (r2.stdout + r2.stderr).strip()
        if r2.returncode == 0 or "up-to-date" in out2 or "Everything" in out2:
            log("  git push OK（重试成功）")
        else:
            log(f"  git push: rc={r2.returncode} {out2[:300]}")
    elif push.returncode == 0 or "up-to-date" in out or "Everything" in out:
        log("  git push OK")
    else:
        log(f"  git push: rc={push.returncode} {out[:300]}")


def main():
    log("=== AI日报自动生成 开始 ===")
    try:
        api_key = get_api_key()
        today = now_beijing()
        date = today.strftime("%Y-%m-%d")
        date_cn = today.strftime("%Y年%m月%d日")
        REPORTS.mkdir(parents=True, exist_ok=True)

        for spec in REPORT_SPECS:
            # 每周排班：有 days 字段的只在指定星期几生成（0=周一 ... 6=周日）
            if "days" in spec and today.weekday() not in spec["days"]:
                continue
            fname = today.strftime(spec["filename"])
            path = REPORTS / fname
            if path.exists():
                log(f"已存在，跳过: {fname}")
                continue
            log(f"生成: {fname}")
            user = spec["user"].format(date=date, date_cn=date_cn)
            content = call_llm(api_key, spec["system"], user)
            # 缩短日报里的所有长链接
            content, short_count = post_process_links(content)
            path.write_text(content + "\n", encoding="utf-8")
            log(f"  ✅ 已写入 {len(content)} 字符（缩短 {short_count} 个链接）")
            time.sleep(5)  # 避免限流

        log("更新网页并推送...")
        r = subprocess.run(["python3", "build_archive.py"], cwd=ARCHIVE, capture_output=True, text=True, timeout=180)
        log(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else f"rc={r.returncode} {r.stderr[:200]}")
        git_push()
        log("=== 完成 ===")
    except Exception as e:
        log(f"❌ 失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
