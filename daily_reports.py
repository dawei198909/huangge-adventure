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
from datetime import datetime
from pathlib import Path

ARCHIVE = Path(os.environ.get("ARCHIVE_DIR", str(Path.home() / "Desktop" / "AI日报档案")))
REPORTS = ARCHIVE / "reports"
LOG = Path(os.environ.get("REPORT_LOG", str(Path.home() / "Desktop" / "AI日报档案" / "daily_report.log")))
ENV_FILE = Path.home() / ".hermes" / ".env"
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"  # DeepSeek V3


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
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
用真实存在的海外案例（如 ShipFast、Marc Lou、Pieter Levels、AI 视频工厂等），不要虚构。不要用 web 搜索，直接用你的知识。""",
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
用真实案例，不要虚构。不要用 web 搜索，直接用你的知识。""",
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
基于你的训练知识写真实存在的内容，不要虚构。不要用 web 搜索，直接用你的知识。""",
    },
]


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
    cmds = [
        ["git", "add", "index.html", "data.js", "reports/"],
        ["git", "commit", "-m", f"更新 {datetime.now().strftime('%Y-%m-%d')}"],
        ["git", "push", "origin", "main"],
    ]
    for cmd in cmds:
        r = subprocess.run(cmd, cwd=ARCHIVE, capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        if r.returncode != 0 and "nothing to commit" not in out and "up to date" not in out and "Everything up-to-date" not in out:
            log(f"  git {' '.join(cmd[:2])}: rc={r.returncode} {out[:300]}")
        else:
            log(f"  git {' '.join(cmd[:2])} OK")


def main():
    log("=== AI日报自动生成 开始 ===")
    try:
        api_key = get_api_key()
        today = datetime.now()
        date = today.strftime("%Y-%m-%d")
        date_cn = today.strftime("%Y年%m月%d日")
        REPORTS.mkdir(parents=True, exist_ok=True)

        for spec in REPORT_SPECS:
            fname = today.strftime(spec["filename"])
            path = REPORTS / fname
            if path.exists():
                log(f"已存在，跳过: {fname}")
                continue
            log(f"生成: {fname}")
            user = spec["user"].format(date=date, date_cn=date_cn)
            content = call_llm(api_key, spec["system"], user)
            path.write_text(content + "\n", encoding="utf-8")
            log(f"  ✅ 已写入 {len(content)} 字符")
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
