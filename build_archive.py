#!/usr/bin/env python3
"""
AI日报档案站生成器
扫描 ~/Desktop/ 下的日报 md 文件，解析并生成静态 index.html
"""
import re
import os
import json
import html
from pathlib import Path
from datetime import datetime

DESKTOP = Path.home() / "Desktop"
ARCHIVE_DIR = Path(os.environ.get("ARCHIVE_DIR", str(DESKTOP / "AI日报档案")))
REPORTS_DIR = ARCHIVE_DIR / "reports"  # 日报源文件存这里
OUTPUT_FILE = ARCHIVE_DIR / "index.html"

DATE_PATTERNS = [
    re.compile(r"(20\d{2})[-_](\d{2})[-_](\d{2})"),
    re.compile(r"(20\d{2})(\d{2})(\d{2})"),
]

def parse_date(filename):
    """从文件名提取日期，返回 (date_str, date_obj)"""
    for pat in DATE_PATTERNS:
        m = pat.search(filename)
        if m:
            y, mo, d = m.group(1), m.group(2), m.group(3)
            return f"{y}-{mo}-{d}", datetime(int(y), int(mo), int(d))
    return None, None

def classify(filename):
    """判断日报类型：money / frontier / apps / radar / industry / pitfall / toolbox"""
    if "赚钱" in filename or "案例" in filename:
        return "money"
    if "应用" in filename:
        return "apps"
    if "前沿" in filename:
        return "frontier"
    if "机会" in filename:
        return "radar"
    if "行业" in filename:
        return "industry"
    if "避坑" in filename:
        return "pitfall"
    if "工具" in filename:
        return "toolbox"
    return None

def scan_reports():
    """扫描日报文件：先查报告目录，再查桌面（向后兼容）"""
    reports = []
    sources = [REPORTS_DIR] if REPORTS_DIR.exists() else []
    sources.append(DESKTOP)  # 兼容旧文件
    for src_dir in sources:
        for f in sorted(src_dir.glob("*日报*.md")):
            name = f.name
            if "测试" in name:
                continue
            date_str, date_obj = parse_date(name)
            rtype = classify(name)
            if not date_str or not rtype:
                continue
            reports.append({
                "date": date_str,
                "date_obj": date_obj,
                "type": rtype,
                "filename": name,
                "path": f,
                "content": f.read_text(encoding="utf-8", errors="ignore"),
            })
    # 去重（按 date+type）
    seen = set()
    deduped = []
    for r in sorted(reports, key=lambda x: x["date_obj"]):
        key = (r["date"], r["type"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped

# ---------- Markdown → HTML 简单转换器 ----------

def md_to_html(md_text):
    """将 Markdown 文本转换为 HTML（支持日报用到的语法子集）"""
    lines = md_text.split("\n")
    out = []
    i = 0
    in_code = False
    code_buf = []
    in_table = False
    table_buf = []
    
    def flush_table():
        nonlocal table_buf, in_table
        if not table_buf:
            return ""
        html_rows = []
        for idx, row in enumerate(table_buf):
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            if idx == 1 and all(re.match(r"^:?-{2,}:?$", c) for c in cells):
                continue  # separator row
            tag = "th" if idx == 0 else "td"
            html_rows.append("<tr>" + "".join(f"<{tag}>{inline(c)}</{tag}>" for c in cells) + "</tr>")
        table_buf = []
        in_table = False
        return '<div class="table-wrap"><table>' + "".join(html_rows) + "</table></div>\n"
    
    def inline(text):
        """行内格式：粗体、行内代码、链接"""
        t = html.escape(text)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"`([^`]+?)`", r"<code>\1</code>", t)
        t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)
        return t
    
    while i < len(lines):
        line = lines[i]
        
        # Code block
        if line.strip().startswith("```"):
            if in_code:
                out.append("<pre><code>" + "\n".join(code_buf) + "</code></pre>")
                code_buf = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(html.escape(line))
            i += 1
            continue
        
        # Table detection
        if "|" in line and line.strip().startswith("|"):
            if not in_table:
                in_table = True
                table_buf = []
            table_buf.append(line)
            i += 1
            continue
        elif in_table:
            out.append(flush_table())
        
        stripped = line.strip()
        
        # Headings
        if re.match(r"^#{1,6} ", stripped):
            level = len(stripped.split(" ")[0])
            title = inline(stripped[level+1:])
            out.append(f'<h{level}>{title}</h{level}>')
        elif stripped == "---" or stripped == "***" or re.match(r"^_{3,}$", stripped):
            out.append('<hr>')
        elif stripped.startswith("> "):
            quote_text = inline(stripped[2:])
            out.append(f"<blockquote>{quote_text}</blockquote>")
        elif re.match(r"^[-*+] ", stripped):
            # List item - simple handling (no nesting)
            out.append(f"<li>{inline(stripped[2:])}</li>")
        elif re.match(r"^\d+\.\s+", stripped):
            item_text = re.sub(r"^\d+\.\s+", "", stripped)
            out.append(f"<li>{inline(item_text)}</li>")
        elif stripped == "":
            out.append("")
        else:
            # Check if previous line was li -> wrap in ul/ol
            out.append(f"<p>{inline(stripped)}</p>")
        i += 1
    
    if in_code and code_buf:
        out.append("<pre><code>" + "\n".join(code_buf) + "</code></pre>")
    if in_table:
        out.append(flush_table())
    
    # Wrap consecutive <li> in <ul>
    result = []
    li_buf = []
    for line in out:
        if line.startswith("<li>"):
            li_buf.append(line)
        else:
            if li_buf:
                result.append("<ul>" + "".join(li_buf) + "</ul>")
                li_buf = []
            result.append(line)
    if li_buf:
        result.append("<ul>" + "".join(li_buf) + "</ul>")
    
    return "\n".join(result)

# ---------- 生成 HTML ----------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📚 AI 日报档案</title>
<style>
/* ===== 主题变量 ===== */
:root {
  --bg: #f6f1e7;
  --bg-soft: #efe8da;
  --card: #fffdf8;
  --card-border: #e2d9c5;
  --text: #3a342a;
  --text-soft: #8a8070;
  --accent: #b07d3e;
  --accent-soft: #e8d9c2;
  --code-bg: #f0e9dc;
  --shadow: rgba(120, 100, 60, 0.08);
  --tag-money: #b07d3e;
  --tag-frontier: #5d7b6f;
  --tag-apps: #4a7fb5;
  --tag-radar: #c0392b;      /* 机会雷达 - 醒目红 */
  --tag-industry: #8e44ad;   /* 行业深潜 - 紫 */
  --tag-pitfall: #e67e22;    /* 避坑指南 - 橙 */
  --tag-toolbox: #16a085;    /* 工具箱 - 青绿 */
}

[data-theme="dark"] {
  --bg: #1f1d19;
  --bg-soft: #28251f;
  --card: #2b2822;
  --card-border: #3d382e;
  --text: #e8e2d6;
  --text-soft: #9a9184;
  --accent: #d4a55c;
  --accent-soft: #4a3f2b;
  --code-bg: #38332a;
  --shadow: rgba(0, 0, 0, 0.25);
}

* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.7;
  transition: background 0.3s, color 0.3s;
}

/* ===== 顶栏 ===== */
.header {
  position: sticky; top: 0; z-index: 100;
  background: var(--bg-soft);
  border-bottom: 1px solid var(--card-border);
  padding: 14px 24px;
  display: flex; align-items: center; gap: 16px;
  flex-wrap: wrap;
}
.header h1 { font-size: 20px; font-weight: 700; flex: 1; min-width: 160px; }
.header h1 span { color: var(--accent); }
.header-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }

.search-box {
  background: var(--card);
  border: 1px solid var(--card-border);
  border-radius: 20px;
  padding: 6px 14px;
  font-size: 14px;
  color: var(--text);
  width: 200px;
  outline: none;
  transition: border 0.2s;
}
.search-box:focus { border-color: var(--accent); }
.search-box::placeholder { color: var(--text-soft); }
.search-btn {
  background: var(--accent); color: #fff; border: none;
  border-radius: 16px; padding: 5px 14px; font-size: 13px; cursor: pointer;
  transition: opacity 0.2s;
}
.search-btn:hover { opacity: 0.85; }

.type-tabs {
  display: flex; gap: 6px;
  background: var(--card);
  border: 1px solid var(--card-border);
  border-radius: 20px;
  padding: 3px;
}
.type-tab {
  border: none; background: transparent;
  padding: 5px 14px; border-radius: 16px;
  font-size: 13px; cursor: pointer; color: var(--text-soft);
  transition: all 0.2s;
}
.type-tab.active { background: var(--accent); color: #fff; }

/* ===== 主布局 ===== */
.main {
  display: flex; min-height: calc(100vh - 62px);
  max-width: 1240px; margin: 0 auto;
}

/* 侧边日历 — 小格子矩阵（桌面端） */
.sidebar.desktop-only {
  width: 200px; flex-shrink: 0;
  border-right: 1px solid var(--card-border);
  padding: 12px 10px;
  background: var(--bg-soft);
  position: sticky; top: 62px;
  height: calc(100vh - 62px);
  overflow-y: auto;
  display: flex; flex-direction: column; align-items: center;
}

/* 侧边日期列表（手机端，默认隐藏） */
.sidebar:not(.desktop-only) {
  display: none;
  width: 100%; flex-shrink: 0;
  border-bottom: 1px solid var(--card-border);
  padding: 8px 12px;
  background: var(--bg-soft);
  max-height: 50vh; overflow-y: auto;
}
.cal-nav-row {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 10px;
}
.cal-nav-row button {
  width: 22px; height: 22px; border: none; border-radius: 4px;
  background: var(--card); color: var(--text); cursor: pointer;
  font-size: 11px; display: flex; align-items: center; justify-content: center;
}
.cal-nav-row button:hover { background: var(--accent-soft); }
.cal-nav-row .cal-year-label {
  font-size: 12px; font-weight: 700; color: var(--text);
  min-width: 50px; text-align: center;
}
.cal-month-strip { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.cal-month-label {
  font-size: 11px; font-weight: 600; color: var(--text-soft);
  text-align: center; margin-top: 2px;
}
.cal-week-row { display: flex; gap: 2px; justify-content: center; }
.cal-dot {
  width: 15px; height: 15px; border-radius: 3px;
  background: var(--card);
  cursor: pointer; position: relative;
  transition: background 0.15s, transform 0.1s;
}
.cal-dot:hover { transform: scale(1.25); z-index: 2; }
.cal-dot.empty { background: transparent; cursor: default; }
.cal-dot.empty:hover { transform: none; }
.cal-dot.today { border: 2px solid var(--accent); }
.cal-dot.selected {
  outline: 3px solid var(--tag-apps);
  outline-offset: 1px;
  transform: scale(1.2);
  z-index: 3;
}
.cal-dot.has-report.money { background: var(--tag-money); }
.cal-dot.has-report.frontier { background: var(--tag-frontier); }
.cal-dot.has-report.apps { background: var(--tag-apps); }
.cal-dot.has-report.radar { background: var(--tag-radar); }
.cal-dot.has-report.industry { background: var(--tag-industry); }
.cal-dot.has-report.pitfall { background: var(--tag-pitfall); }
.cal-dot.has-report.toolbox { background: var(--tag-toolbox); }
.cal-dot.has-report.today { opacity: 1; box-shadow: 0 0 5px rgba(176,125,62,0.4); }

/* 未读标记 */
.cal-dot.unread::after {
  content: ""; position: absolute;
  top: 1px; right: 1px;
  width: 5px; height: 5px;
  background: #e05; border-radius: 50%;
}
.cal-dot .tooltip {
  display: none; position: absolute;
  bottom: 130%; left: 50%; transform: translateX(-50%);
  background: var(--text); color: var(--bg);
  padding: 2px 6px; border-radius: 4px;
  font-size: 10px; white-space: nowrap; pointer-events: none; z-index: 10;
}
.cal-dot:hover .tooltip { display: block; }

/* 内容区 */
.content { flex: 1; padding: 32px 36px; max-width: 920px; }

.report-card {
  background: var(--card);
  border: 1px solid var(--card-border);
  border-radius: 16px;
  padding: 0;
  margin-bottom: 32px;
  box-shadow: 0 4px 20px var(--shadow);
  overflow: hidden;
  transition: transform 0.2s, box-shadow 0.2s;
}
.report-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 28px var(--shadow);
}
.report-card.money { border-left: 4px solid var(--tag-money); }
.report-card.frontier { border-left: 4px solid var(--tag-frontier); }
.report-card.apps { border-left: 4px solid var(--tag-apps); }
.report-card.radar { border-left: 4px solid var(--tag-radar); }
.report-card.industry { border-left: 4px solid var(--tag-industry); }
.report-card.pitfall { border-left: 4px solid var(--tag-pitfall); }
.report-card.toolbox { border-left: 4px solid var(--tag-toolbox); }
.report-head {
  display: flex; align-items: center; gap: 12px;
  margin-bottom: 0; flex-wrap: wrap;
  padding: 22px 30px 0 30px;
  cursor: pointer;
}
.report-head .type-badge {
  padding: 3px 12px; border-radius: 12px;
  font-size: 12px; font-weight: 600; color: #fff;
}
.type-badge.money { background: var(--tag-money); }
.type-badge.frontier { background: var(--tag-frontier); }
.type-badge.apps { background: var(--tag-apps); }
.type-badge.radar { background: var(--tag-radar); }
.type-badge.industry { background: var(--tag-industry); }
.type-badge.pitfall { background: var(--tag-pitfall); }
.type-badge.toolbox { background: var(--tag-toolbox); }
.report-head .report-date { font-size: 18px; font-weight: 700; }
.report-head .report-file { font-size: 12px; color: var(--text-soft); margin-left: auto; }

.report-body { padding: 4px 30px 28px 30px; }

.report-body h1, .report-body h2 { margin: 28px 0 12px; }
.report-body h1 { font-size: 26px; font-weight: 700; line-height: 1.35; }
.report-body h2 { font-size: 19px; font-weight: 600; color: var(--accent); line-height: 1.45; cursor: pointer; display: flex; align-items: center; gap: 8px; }
.report-body h2:hover { opacity: 0.8; }
.report-body h2::after {
  content: "▾"; font-size: 18px; font-weight: 700; transition: transform 0.2s; color: var(--accent); margin-left: auto;
}
.report-body h2.collapsed::after { transform: rotate(-90deg); }
.section-body { transition: max-height 0.3s ease, opacity 0.3s; overflow: hidden; }
.section-body.hidden { max-height: 0; opacity: 0; }

/* 信息来源折叠框 */
.source-scroll {
  max-height: 130px;
  overflow-y: auto;
  border: 1px solid var(--card-border);
  border-radius: 8px;
  padding: 10px 14px;
  background: var(--bg-soft);
  margin: 8px 0;
  transition: max-height 0.3s ease;
}
.source-scroll.open { max-height: none; }
.source-scroll ul { margin: 0; padding-left: 20px; }
.source-scroll li { margin: 4px 0; font-size: 13px; }
.source-toggle {
  display: inline-block;
  margin: 6px 0 0 0;
  padding: 4px 12px;
  font-size: 12px;
  border: 1px solid var(--card-border);
  border-radius: 12px;
  background: var(--card);
  color: var(--text-soft);
  cursor: pointer;
}
.source-toggle:hover { border-color: var(--accent); color: var(--accent); }

/* 分析层 — 金色左边框突出 */
.section-body.insight {
  border-left: 3px solid #c99874;
  padding-left: 16px; margin: 12px 0;
  background: linear-gradient(90deg, rgba(201,152,116,0.08), transparent);
  border-radius: 0 6px 6px 0;
}

/* 卡片内目录 */
.report-toc {
  padding: 12px 30px 0 30px; font-size: 13px; color: var(--text-soft);
  display: flex; flex-wrap: wrap; gap: 6px;
}
.report-toc a {
  background: var(--bg-soft); border: 1px solid var(--card-border);
  border-radius: 14px; padding: 3px 12px; font-size: 12px; cursor: pointer;
  text-decoration: none; color: var(--text); transition: all 0.15s;
}
.report-toc a:hover { background: var(--accent); color: #fff; border-color: var(--accent); }

/* 移动端优化 */
@media (max-width: 640px) {
  /* 手机端专用 */
  .header { padding: 10px 12px; gap: 8px; }
  .header-inner { 
    display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  }
  .header h1 { font-size: 18px; min-width: auto; flex: none; }
  .header-actions { gap: 4px; }
  .type-tabs { gap: 3px; }
  .type-tab { padding: 3px 8px; font-size: 11px; border-radius: 10px; }
  .search-box { width: 100px; font-size: 12px; padding: 5px 10px; }
  .search-btn { font-size: 11px; padding: 5px 10px; border-radius: 12px; }
  
  /* 堆叠布局 */
  .main { flex-direction: column; max-width: 100%; }
  
  /* 侧边栏 → 顶部横向日期条（桌面版格子隐藏） */
  .sidebar.desktop-only { display: none !important; }
  .sidebar:not(.desktop-only) { display: block; }

  /* 按月折叠列表 */
  .month-group { margin-bottom: 4px; }
  .month-head {
    display: flex; align-items: center; gap: 8px;
    padding: 10px 12px; cursor: pointer; border-radius: 8px;
    background: var(--card); font-size: 14px; font-weight: 600;
    border: 1px solid var(--card-border);
  }
  .month-head .arrow { transition: transform 0.2s; font-size: 10px; }
  .month-head.open .arrow { transform: rotate(90deg); }
  .month-head .count { margin-left: auto; font-size: 12px; color: var(--text-soft); }
  .date-list { display: none; list-style: none; padding: 4px 0 4px 8px; margin: 0; }
  .date-list.open { display: block; }
  .date-item {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 14px; cursor: pointer; border-radius: 6px;
    font-size: 14px; transition: background 0.15s;
  }
  .date-item:hover, .date-item.active { background: var(--accent-soft); }
  .date-item .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .date-item .dot.money { background: var(--tag-money); }
  .date-item .dot.frontier { background: var(--tag-frontier); }
  .date-item .dot.apps { background: var(--tag-apps); }
  .date-item .dot.radar { background: var(--tag-radar); }
  .date-item .dot.industry { background: var(--tag-industry); }
  .date-item .dot.pitfall { background: var(--tag-pitfall); }
  .date-item .dot.toolbox { background: var(--tag-toolbox); }
  .date-item .dot.both { background: linear-gradient(135deg, var(--tag-money) 50%, var(--tag-frontier) 50%); }
  .date-item .label { flex: 1; }
  .date-item .today-tag { font-size: 10px; color: #4a9; font-weight: 600; }
  .date-item .item-count { font-size: 12px; color: var(--text-soft); }
  
  /* 内容区全宽 */
  .content { padding: 8px 8px 80px; max-width: 100%; }
  .report-card { margin-bottom: 10px; border-radius: 10px; }
  .report-card:hover { transform: none; }
  .report-head { padding: 12px 12px 0 12px; gap: 6px; }
  .type-badge { font-size: 10px; padding: 2px 7px; border-radius: 8px; }
  .report-head .report-date { font-size: 14px; }
  .report-head .report-file { font-size: 10px; display: none; }
  .report-body { padding: 6px 12px 18px 12px; }
  .report-body h1 { font-size: 19px; }
  .report-body h2 { font-size: 15px; }
  .report-body h2::after { font-size: 14px; }
  .report-body h3 { font-size: 14px; }
  .report-body p, .report-body li { font-size: 14px; line-height: 1.75; }
  .report-body table { font-size: 11px; }
  .report-body th, .report-body td { padding: 5px 7px; }
  .report-toc { padding: 6px 12px 0 12px; gap: 4px; }
  .report-toc a { font-size: 10px; padding: 2px 8px; border-radius: 10px; }
  .section-body.insight { padding-left: 10px; margin: 6px 0; border-width: 2px; }
  .report-card .type-badge { font-size: 10px; }
  
  #backToTop { width: 38px; height: 38px; font-size: 16px; bottom: 14px; right: 10px; }
  mark { padding: 0 1px; }
}

@media (max-width: 800px) and (min-width: 641px) {
  /* 平板端 */
  .main { flex-direction: column; }
  .sidebar {
    width: 100%; position: static; height: auto;
    border-right: none; border-bottom: 1px solid var(--card-border);
    padding: 10px 8px; flex-direction: column; gap: 4px;
    align-items: flex-start; overflow-x: auto;
  }
  .cal-month-strip { flex-direction: column; align-items: flex-start; }
  .content { padding: 16px 20px; }
}
.report-body h3 { font-size: 16px; margin: 20px 0 8px; font-weight: 600; }
.report-body p { margin: 8px 0; font-size: 15px; line-height: 1.85; }
.report-body ul, .report-body ol { margin: 10px 0 10px 24px; font-size: 15px; line-height: 1.85; }
.report-body li { margin: 4px 0; }
.report-body blockquote {
  border-left: 3px solid var(--accent);
  background: var(--accent-soft);
  padding: 10px 16px; border-radius: 0 10px 10px 0;
  margin: 12px 0;
  font-size: 15px;
}
.report-body code {
  background: var(--code-bg);
  padding: 2px 6px; border-radius: 5px;
  font-size: 13px;
  font-family: "SF Mono", Menlo, Consolas, monospace;
}
.report-body pre {
  background: var(--code-bg);
  padding: 14px 16px; border-radius: 10px;
  overflow-x: auto; margin: 12px 0;
  font-size: 13px; line-height: 1.5;
}
.report-body pre code { background: none; padding: 0; }
.report-body hr { border: none; border-top: 1px solid var(--card-border); margin: 20px 0; }
.report-body table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }
.report-body th {
  background: var(--accent-soft); text-align: left;
  padding: 8px 10px; font-weight: 600;
}
.report-body td { padding: 8px 10px; border-bottom: 1px solid var(--card-border); }
.table-wrap { overflow-x: auto; }
.report-body a { color: var(--accent); text-decoration: none; }
.report-body a:hover { text-decoration: underline; }

.empty-state {
  text-align: center; padding: 80px 20px;
  color: var(--text-soft);
}
.empty-state .big { font-size: 48px; margin-bottom: 12px; }

/* 高亮搜索 */
mark { background: #f2d98c; color: #3a342a; padding: 0 2px; border-radius: 3px; }
[data-theme="dark"] mark { background: #6b5a2a; color: #fff; }

/* 回到顶部 */
.back-to-top {
  position: fixed; bottom: 28px; right: 28px;
  width: 44px; height: 44px; border-radius: 50%;
  background: var(--accent); color: #fff; border: none;
  font-size: 20px; cursor: pointer;
  opacity: 0; transform: translateY(16px);
  pointer-events: none;
  transition: opacity 0.3s, transform 0.3s;
  box-shadow: 0 4px 14px rgba(0,0,0,0.18);
  z-index: 200;
}
.back-to-top.visible {
  opacity: 1; transform: translateY(0);
  pointer-events: auto;
}
.back-to-top:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(0,0,0,0.25); }

/* 响应式 */
</style>
</head>
<body>
<div class="header">
  <h1>📚 AI 日报档案 <span>· 每日一读</span></h1>
  <div class="header-actions">
    <div class="type-tabs" id="typeTabs">
      <button class="type-tab" data-type="money">💰 赚钱</button>
      <button class="type-tab" data-type="apps">🔧 应用</button>
      <button class="type-tab" data-type="frontier">📡 前沿</button>
      <button class="type-tab" data-type="radar">🎯 机会</button>
      <button class="type-tab" data-type="industry">🏭 行业</button>
      <button class="type-tab" data-type="pitfall">⚠️ 避坑</button>
      <button class="type-tab" data-type="toolbox">🧰 工具</button>
    </div>
    <input class="search-box" id="searchBox" type="text" placeholder="🔍 搜索日报内容...">
    <button class="search-btn" id="searchBtn">搜索</button>
  </div>
</div>

<div class="main">
  <aside class="sidebar" id="dateList"></aside>
  <aside class="sidebar desktop-only" id="desktopSidebar">
    <div class="cal-nav-row">
      <button id="prevMonth" title="上月">◀</button>
      <span class="cal-year-label" id="calYearLabel"></span>
      <button id="nextMonth" title="下月">▶</button>
    </div>
    <div class="cal-month-strip" id="calMonthStrip"></div>
  </aside>
  <main class="content" id="content"></main>
</div>

<script src="data.js"></script>

<button class="back-to-top" id="backToTop" title="回到顶部" onclick="window.scrollTo({top:0,behavior:'smooth'})">↑</button>

<script>
// ===== 状态 =====
let currentDate = null;
let currentType = null;
let searchQuery = "";
// ===== 工具 =====
function getDates() {
  const dates = {};
  REPORTS.forEach(r => {
    if (!dates[r.date]) dates[r.date] = { money: 0, frontier: 0 };
    dates[r.date][r.type]++;
  });
  return Object.keys(dates).sort().reverse();
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function highlightText(text, query) {
  if (!query) return text;
  const esc = escapeHtml(text);
  const escQuery = escapeHtml(query).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp("(" + escQuery + ")", "gi");
  return esc.replace(re, "<mark>$1</mark>");
}

// ===== 渲染 =====
// ===== 小格子日历 =====
let calStartMonth;

function getReportDates() {
  const map = {};  // date → {money: bool, frontier: bool, apps: bool}
  REPORTS.forEach(r => {
    if (!map[r.date]) map[r.date] = {};
    map[r.date][r.type] = true;
  });
  return map;
}

function renderCalendar() {
  const strip = document.getElementById("calMonthStrip");
  const label = document.getElementById("calYearLabel");
  const reportDates = getReportDates();
  const today = new Date();
  const todayStr = today.toISOString().slice(0, 10);
  const thisMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;

  if (!calStartMonth) calStartMonth = thisMonth;
  const [sy, sm] = calStartMonth.split("-").map(Number);
  label.textContent = `${sy}年`;

  const monthBlocks = [];
  let y = sy, m = sm;
  for (let i = 0; i < 6; i++) {
    monthBlocks.push({y, mo: m});
    m--; if (m < 1) { m = 12; y--; }
  }

  const monthNames = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"];

  strip.innerHTML = monthBlocks.map(b => {
    const daysInMonth = new Date(b.y, b.mo, 0).getDate();
    const firstWeekday = new Date(b.y, b.mo - 1, 1).getDay();
    const rows = [];
    let cur = [];
    for (let d = 0; d < firstWeekday; d++) cur.push('<span class="cal-dot empty"></span>');
    for (let day = 1; day <= daysInMonth; day++) {
      const ds = `${b.y}-${String(b.mo).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      const info = reportDates[ds];
      const typeCls = info ? (info.apps ? "apps" : (info.money ? "money" : (info.frontier ? "frontier" : (info.radar ? "radar" : (info.industry ? "industry" : (info.pitfall ? "pitfall" : "toolbox")))))) : "";
      const has = !!info;
      const isToday = ds === todayStr;
      const isSelected = ds === currentDate;
      cur.push(
        `<span class="cal-dot${has ? " has-report "+typeCls : ""}${isToday ? " today" : ""}${isSelected ? " selected" : ""}"
              data-date="${ds}" data-has="${has ? 1 : 0}">
          <span class="tooltip">${ds}${has ? (info.money?" 💰":"")+(info.frontier?" 📡":"")+(info.apps?" 🔧":"")+(info.radar?" 🎯":"")+(info.industry?" 🏭":"")+(info.pitfall?" ⚠️":"")+(info.toolbox?" 🧰":"") : ""}</span>
        </span>`
      );
      if (cur.length === 7) { rows.push(`<div class="cal-week-row">${cur.join("")}</div>`); cur = []; }
    }
    if (cur.length > 0) rows.push(`<div class="cal-week-row">${cur.join("")}</div>`);
    return `<div class="cal-month-label">${monthNames[b.mo - 1]}</div>${rows.join("")}`;
  }).join("");

  strip.querySelectorAll(".cal-dot:not(.empty)").forEach(el => {
    el.addEventListener("click", () => {
      currentDate = el.dataset.date;
      currentType = null;
      document.querySelectorAll(".type-tab").forEach(t => t.classList.remove("active"));
      searchQuery = ""; document.getElementById("searchBox").value = "";
      // 标记已读
      const lastVisit = localStorage.getItem("lastVisitDate") || "";
      if (el.dataset.date > lastVisit) localStorage.setItem("lastVisitDate", todayStr);
      renderCalendar();
      renderMobileDates();
      renderContent();
      window.scrollTo({top: 0, behavior: "smooth"});  // 切换日期滚回顶部
    });
  });

  // ===== 未读标记 =====
  const lastVisit = localStorage.getItem("lastVisitDate") || "";
  strip.querySelectorAll(`.cal-dot[data-date]`).forEach(el => {
    if (el.dataset.date > lastVisit && el.dataset.has === "1") el.classList.add("unread");
  });
}

// ===== 手机版：按月折叠日期列表 =====
function renderMobileDates() {
  const list = document.getElementById("dateList");
  const today = new Date().toISOString().slice(0, 10);
  const byMonth = {};
  REPORTS.forEach(r => {
    const m = r.date.slice(0, 7);
    if (!byMonth[m]) byMonth[m] = [];
    byMonth[m].push(r);
  });
  const months = Object.keys(byMonth).sort().reverse();
  // 手机端默认全部折叠，不自动展开任何月份
  const openMonths = {};
  document.querySelectorAll("#dateList .month-head.open").forEach(el => openMonths[el.dataset.month] = true);

  const monthNames = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"];

  list.innerHTML = months.map(m => {
    const [y, mo] = m.split("-");
    const entries = byMonth[m];
    const uniqueDates = [...new Set(entries.map(r => r.date))].sort().reverse();
    const totalArticles = entries.length;
    const isOpen = openMonths[m] === true;

    return `<div class="month-group">
      <div class="month-head ${isOpen ? "open" : ""}" data-month="${m}">
        <span class="arrow">▶</span>
        <span>${y}年${monthNames[parseInt(mo) - 1]}</span>
        <span class="count">${totalArticles}篇</span>
      </div>
      <ul class="date-list ${isOpen ? "open" : ""}">
        ${uniqueDates.map(d => {
          const items = entries.filter(r => r.date === d);
          const types = [...new Set(items.map(r => r.type))];
          const dotCls = types.length > 1 ? "both" : types[0];
          const isActive = d === currentDate;
          return `<li class="date-item ${isActive ? "active" : ""}" data-date="${d}">
            <span class="dot ${dotCls}"></span>
            <span class="label">${d.slice(5)}</span>
            ${d === today ? '<span class="today-tag">今天</span>' : ""}
            <span class="item-count">${items.length}篇</span>
          </li>`;
        }).join("")}
      </ul>
    </div>`;
  }).join("");

  list.querySelectorAll(".month-head").forEach(el => {
    el.addEventListener("click", () => {
      el.classList.toggle("open");
      el.nextElementSibling.classList.toggle("open");
    });
  });
  list.querySelectorAll(".date-item").forEach(el => {
    el.addEventListener("click", () => {
      currentDate = el.dataset.date;
      currentType = null;
      document.querySelectorAll(".type-tab").forEach(t => t.classList.remove("active"));
      searchQuery = ""; document.getElementById("searchBox").value = "";
      renderMobileDates();
      renderCalendar();
      renderContent();
      window.scrollTo({top: 0, behavior: "smooth"});  // 切换日期滚回顶部
    });
  });
}

function renderContent() {
  const container = document.getElementById("content");
  let reports = REPORTS;
  if (searchQuery) currentDate = null;  // 搜索时忽略日期
  if (currentDate) reports = reports.filter(r => r.date === currentDate);
  if (currentType) reports = reports.filter(r => r.type === currentType);
  if (searchQuery) {
    const q = searchQuery.toLowerCase();
    reports = reports.filter(r => {
      const t = r.content.toLowerCase();
      // 空格分关键词
      const keywords = q.split(/\s+/).filter(k => k);
      if (keywords.length === 0) return true;
      // 每个关键词：子串匹配 OR 逐字匹配（中文无空格场景）
      return keywords.every(kw => {
        if (t.includes(kw)) return true;
        // 中文逐字匹配：把关键词拆成单字，检查是否按序出现在内容中
        const chars = [...kw].filter(c => /[\u4e00-\u9fff]/.test(c)); // 仅中文字
        if (chars.length < 2) return false;
        let pos = 0;
        for (const ch of chars) {
          pos = t.indexOf(ch, pos);
          if (pos === -1) return false;
          pos++;
        }
        return true;
      });
    });
  }
  
  if (reports.length === 0) {
    container.innerHTML = `<div class="empty-state">
      <div class="big">📭</div>
      <p>${searchQuery ? "没有找到匹配的内容" : "这一天没有日报"}</p>
    </div>`;
    return;
  }
  
  // 按日期倒序渲染
  const byDate = {};
  reports.forEach(r => {
    if (!byDate[r.date]) byDate[r.date] = [];
    byDate[r.date].push(r);
  });

  // ===== 按阅读习惯排序：同一天内停留久的板块排前面 =====
  try {
    const habit = JSON.parse(localStorage.getItem("aiBoardTime") || "{}");
    Object.keys(byDate).forEach(d => {
      if (byDate[d].length > 1) {
        byDate[d].sort((a, b) => (habit[b.type] || 0) - (habit[a.type] || 0));
      }
    });
  } catch (e) {}
  
  const dates = Object.keys(byDate).sort().reverse();
  container.innerHTML = dates.map(d => {
    return byDate[d].map(r => {
      const badgeText = {
        money: "💰 赚钱案例",
        apps: "🔧 应用场景",
        frontier: "📡 前沿情报",
        radar: "🎯 机会雷达",
        industry: "🏭 行业深潜",
        pitfall: "⚠️ 避坑指南",
        toolbox: "🧰 工具箱",
      }[r.type] || r.type;
      return `
      <article class="report-card ${r.type}" data-date="${r.date}" data-type="${r.type}">
        <div class="report-head">
          <span class="type-badge ${r.type}">${badgeText}</span>
          <span class="report-date">${r.date}</span>
          <span class="report-file">${escapeHtml(r.filename)}</span>
        </div>
        <div class="report-body">${r.html}</div>
      </article>`;
    }).join("");
  }).join("");

  // ===== 可折叠标题 =====
  container.querySelectorAll(".report-body").forEach(body => {
    const h2s = body.querySelectorAll("h2");
    h2s.forEach(h2 => {
      h2.addEventListener("click", () => {
        h2.classList.toggle("collapsed");
        let next = h2.nextElementSibling;
        while (next && next.tagName !== "H2") {
          if (next.classList.contains("section-body")) next.classList.toggle("hidden");
          next = next.nextElementSibling;
        }
      });
    });
    h2s.forEach(h2 => {
      const wrapper = document.createElement("div");
      wrapper.className = "section-body";
      let next = h2.nextElementSibling;
      while (next && next.tagName !== "H2") {
        const toMove = next;
        next = next.nextElementSibling;
        wrapper.appendChild(toMove);
      }
      h2.parentNode.insertBefore(wrapper, h2.nextElementSibling || h2.nextSibling);
    });
  });

  // ===== 分析层识别 =====
  const analysisKW = ["具体做法","国内可复制","赚钱逻辑","收入情况","一句话建议","可复用","操作技巧","落地路径","怎么做","可行性","变现","成本","门槛"];
  container.querySelectorAll(".report-body h2").forEach(h2 => {
    const txt = h2.textContent;
    if (analysisKW.some(k => txt.includes(k))) {
      const section = h2.nextElementSibling;
      if (section && section.classList.contains("section-body")) section.classList.add("insight");
    }
  });

  // ===== 卡片目录 =====
  container.querySelectorAll(".report-card").forEach(card => {
    const body = card.querySelector(".report-body");
    if (!body) return;
    const h2s = body.querySelectorAll("h2");
    if (h2s.length < 2) return;
    const toc = document.createElement("div");
    toc.className = "report-toc";
    h2s.forEach(h2 => {
      const link = document.createElement("a");
      link.textContent = h2.textContent.trim();
      link.addEventListener("click", () => h2.scrollIntoView({behavior:"smooth",block:"start"}));
      toc.appendChild(link);
    });
    body.insertBefore(toc, body.firstChild);
  });

  // ===== 信息来源折叠框：链接超过 3 个 → 可滚动小框 =====
  container.querySelectorAll(".report-body h2").forEach(h2 => {
    if (!h2.textContent.includes("信息来源")) return;
    // 找 h2 后面的内容容器（可能是 section-body）
    let box = h2.nextElementSibling;
    while (box && !box.classList || (box && !box.classList.contains("section-body"))) box = box.nextElementSibling;
    if (!box) return;
    const links = box.querySelectorAll("a");
    if (links.length <= 3) return;
    // 包一层可滚动容器
    const wrapper = document.createElement("div");
    wrapper.className = "source-scroll";
    box.parentNode.insertBefore(wrapper, box);
    wrapper.appendChild(box);
    // 加展开/收起按钮
    const btn = document.createElement("button");
    btn.className = "source-toggle";
    btn.textContent = `▾ 展开全部（${links.length} 条）`;
    btn.addEventListener("click", () => {
      const open = wrapper.classList.toggle("open");
      btn.textContent = open ? `▴ 收起（${links.length} 条）` : `▾ 展开全部（${links.length} 条）`;
    });
    wrapper.after(btn);
  });

  // ===== 搜索高亮 =====
  if (searchQuery && reports.length > 0) {
    const keywords = searchQuery.trim().split(/\s+/).filter(k => k.length > 0);
    keywords.forEach(kw => {
      const chars = [...kw];
      const reStr = chars.map(c => c.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\s*");
      const re = new RegExp("(?![^<]*>)(" + reStr + ")", "gi");
      // 只在文本节点区域替换（排除标签内的属性值）
      container.querySelectorAll(".report-card *").forEach(el => {
        el.childNodes.forEach(child => {
          if (child.nodeType === 3) {
            const txt = child.textContent;
            if (re.test(txt)) {
              re.lastIndex = 0;
              const span = document.createElement("span");
              span.innerHTML = txt.replace(re, "<mark>$1</mark>");
              child.replaceWith(span);
            }
          }
        });
      });
    });
    // 滚动到第一个高亮
    const firstMark = container.querySelector("mark");
    if (firstMark) firstMark.scrollIntoView({behavior: "smooth", block: "center"});
  }
}

// ===== 搜索 =====
function doSearch() {
  searchQuery = document.getElementById("searchBox").value.trim();
  currentType = null;
  document.querySelectorAll(".type-tab").forEach(t => t.classList.remove("active"));
  renderCalendar();
  renderMobileDates();
  renderContent();
}

document.getElementById("searchBtn").addEventListener("click", doSearch);
document.getElementById("searchBox").addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); doSearch(); }
});

// ===== 类型切换 =====
document.getElementById("typeTabs").addEventListener("click", e => {
  const tab = e.target.closest(".type-tab");
  if (!tab) return;
  // 如果点的是已选中的标签，取消选中（显示全部）
  if (tab.classList.contains("active")) {
    tab.classList.remove("active");
    currentType = null;
    currentDate = getDates()[0];
  } else {
    document.querySelectorAll(".type-tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    currentType = tab.dataset.type;
    currentDate = null;
  }
  searchQuery = ""; document.getElementById("searchBox").value = "";
  renderCalendar();
  renderMobileDates();
  renderContent();
  window.scrollTo({top: 0, behavior: "smooth"});  // 切换类型滚回顶部
});

// ===== 阅读习惯跟踪 =====
let habitTimer = null;
let currentViewType = null;

function getHabit() {
  try { return JSON.parse(localStorage.getItem("aiBoardTime") || "{}"); } catch (e) { return {}; }
}

// 每 2 秒：累加当前视口中心板块的停留时长
function startHabitTracking() {
  if (habitTimer) return;
  habitTimer = setInterval(() => {
    const card = getCenterCard();
    if (!card || !card.dataset.type) return;
    const habit = getHabit();
    habit[card.dataset.type] = (habit[card.dataset.type] || 0) + 2;
    try { localStorage.setItem("aiBoardTime", JSON.stringify(habit)); } catch (e) {}
  }, 2000);
}

// 滚动联动高亮 + 记录位置（节流 300ms）
function trackScroll() {
  let ticking = false;
  window.addEventListener("scroll", () => {
    if (!ticking) {
      ticking = true;
      requestAnimationFrame(() => {
        const card = getCenterCard();
        if (card && card.dataset.type) {
          highlightTab(card.dataset.type);
          // 记录阅读位置（仅当日）
          try {
            const today = new Date().toISOString().slice(0, 10);
            localStorage.setItem("aiLastPos", JSON.stringify({
              date: card.dataset.date,
              scrollY: window.scrollY,
              seenToday: today,
            }));
          } catch (e) {}
        }
        ticking = false;
      });
    }
  });
}

function getCenterCard() {
  const cards = document.querySelectorAll("#content .report-card");
  if (!cards.length) return null;
  const mid = window.innerHeight / 2;
  let best = null, bestDist = Infinity;
  cards.forEach(c => {
    const r = c.getBoundingClientRect();
    const center = r.top + r.height / 2;
    const dist = Math.abs(center - mid);
    if (dist < bestDist) { bestDist = dist; best = c; }
  });
  return best;
}

// 高亮顶部对应类型标签（联动）
function highlightTab(type) {
  document.querySelectorAll(".type-tab").forEach(t => {
    t.classList.toggle("active", t.dataset.type === type);
  });
}

// 恢复上次阅读位置（仅当天有效）
function restorePosition() {
  try {
    const pos = JSON.parse(localStorage.getItem("aiLastPos") || "{}");
    const today = new Date().toISOString().slice(0, 10);
    if (pos.seenToday === today && pos.date && typeof pos.scrollY === "number") {
      setTimeout(() => window.scrollTo({top: pos.scrollY, behavior: "auto"}), 300);
    }
  } catch (e) {}
}

// ===== 初始化 =====
(function init() {
  const today = new Date();
  calStartMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
  const dates = getDates();
  if (dates.length > 0) currentDate = dates[0];
  renderCalendar();
  renderMobileDates();
  renderContent();

  // 默认视图自动检测：如果当天只有一种类型，自动高亮对应标签
  const todayReports = REPORTS.filter(r => r.date === dates[0]);
  const todayTypes = [...new Set(todayReports.map(r => r.type))];  if (todayTypes.length === 1) {
    currentType = todayTypes[0];
    const tab = document.querySelector(`.type-tab[data-type="${currentType}"]`);
    if (tab) tab.classList.add("active");
  }

  // ===== 阅读习惯跟踪 + 滚动联动 + 位置恢复 =====
  startHabitTracking();
  trackScroll();
  restorePosition();

  // 月历翻页
  document.getElementById("prevMonth").addEventListener("click", () => {
    const [y, m] = calStartMonth.split("-").map(Number);
    const prev = new Date(y, m - 2, 1);
    calStartMonth = `${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, "0")}`;
    renderCalendar();
    renderMobileDates();
  });
  document.getElementById("nextMonth").addEventListener("click", () => {
    const [y, m] = calStartMonth.split("-").map(Number);
    const next = new Date(y, m, 1);
    const nm = `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`;
    if (nm <= `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`) calStartMonth = nm;
    renderCalendar();
    renderMobileDates();
  });

  // 回到顶部
  const backBtn = document.getElementById("backToTop");
  window.addEventListener("scroll", () => backBtn.classList.toggle("visible", window.scrollY > 300), {passive: true});
})();
</script>
</body>
</html>
"""

def build():
    reports = scan_reports()
    print(f"发现 {len(reports)} 份日报")
    
    # 为每份日报生成 HTML，并预计算纯文本用于搜索
    data = []
    for r in reports:
        html_content = md_to_html(r["content"])
        # 纯文本（去 HTML 标签）用于搜索
        plain = re.sub(r"<[^>]+>", "", html_content)
        data.append({
            "date": r["date"],
            "type": r["type"],
            "filename": r["filename"],
            "content": plain,
            "html": html_content,
        })
    
    data_json = json.dumps(data, ensure_ascii=False)
    
    # 数据写入独立 data.js（避免内嵌 script 的 HTML 解析问题）
    data_js_path = ARCHIVE_DIR / "data.js"
    data_js_path.write_text("// 由 build_archive.py 自动生成\nwindow.REPORTS = " + data_json + ";\n", encoding="utf-8")
    
    output = HTML_TEMPLATE.replace("__DATA__", data_json)
    
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(output, encoding="utf-8")
    print(f"✅ 已生成: {OUTPUT_FILE}")
    print(f"   文件大小: {OUTPUT_FILE.stat().st_size / 1024:.1f} KB")
    
    # 按日期/类型统计
    from collections import Counter
    stats = Counter((r["date"], r["type"]) for r in reports)
    for k in sorted(stats, reverse=True):
        print(f"   {k[0]} {k[1]}: {stats[k]} 份")

if __name__ == "__main__":
    build()
