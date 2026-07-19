#!/usr/bin/env python3
"""將 API.md 轉成零相依、可直接發布的 api.html。"""

from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LOCALES = (
    {
        "source": "API.md",
        "target": "api.html",
        "lang": "zh-Hant",
        "title": "Identity Service API 文件",
        "description": "Identity Service 公開 API 文件：Headers、Payload、Response、錯誤碼與安全規範",
        "home": "首頁",
        "quick": "快速上手",
        "quick_file": "api.html#13-最小串接檢查",
        "download": "下載 API.md",
        "toc": "文件目錄",
        "footer": "Identity Service 公開 API 文件 · 更新時間：2026-07-20（Asia/Taipei）",
    },
    {
        "source": "API.zh-Hans.md",
        "target": "api.zh-Hans.html",
        "lang": "zh-Hans",
        "title": "Identity Service API 文档",
        "description": "Identity Service 公开 API 文档：Headers、Payload、Response、错误码与安全规范",
        "home": "首页",
        "quick": "快速入门",
        "quick_file": "api.zh-Hans.html#13-最小串接检查",
        "download": "下载 API.zh-Hans.md",
        "toc": "文档目录",
        "footer": "Identity Service 公开 API 文档 · 更新时间：2026-07-20（Asia/Taipei）",
    },
    {
        "source": "API.en.md",
        "target": "api.en.html",
        "lang": "en",
        "title": "Identity Service API Documentation",
        "description": "Identity Service public API documentation covering headers, payloads, responses, error codes, and security requirements",
        "home": "Home",
        "quick": "Quick start",
        "quick_file": "api.en.html#13-minimum-integration-checklist",
        "download": "Download API.en.md",
        "toc": "Contents",
        "footer": "Identity Service public API documentation · Updated: 2026-07-20 (Asia/Taipei)",
    },
)


def slugify(text: str) -> str:
    value = re.sub(r"`", "", text).lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value).strip("-")
    return value or "section"


def inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"`([^`]+)`", r'<code translate="no">\1</code>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2">\1</a>',
        escaped,
    )
    return escaped


def render_markdown(source: str) -> tuple[str, str]:
    lines = source.splitlines()
    out: list[str] = []
    toc: list[str] = []
    paragraph: list[str] = []
    list_kind: str | None = None
    in_code = False
    code_lang = ""
    code_lines: list[str] = []
    used_ids: dict[str, int] = {}

    def flush_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_kind
        if list_kind:
            out.append(f"</{list_kind}>")
            list_kind = None

    def unique_id(title: str) -> str:
        base = slugify(title)
        used_ids[base] = used_ids.get(base, 0) + 1
        return base if used_ids[base] == 1 else f"{base}-{used_ids[base]}"

    index = 0
    while index < len(lines):
        line = lines[index]

        if in_code:
            if line.startswith("```"):
                css = f' class="language-{html.escape(code_lang)}"' if code_lang else ""
                out.append(f"<pre><code{css}>{html.escape(chr(10).join(code_lines))}</code></pre>")
                in_code = False
                code_lang = ""
                code_lines.clear()
            else:
                code_lines.append(line)
            index += 1
            continue

        if line.startswith("```"):
            flush_paragraph()
            close_list()
            in_code = True
            code_lang = line[3:].strip()
            index += 1
            continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            title = heading.group(2)
            section_id = unique_id(title)
            classes = ' class="endpoint-title"' if level == 3 and re.match(r"(GET|POST|PATCH) ", title) else ""
            out.append(f'<h{level} id="{section_id}"{classes}>{inline(title)}</h{level}>')
            if level in (2, 3):
                toc.append(
                    f'<a class="toc-l{level}" href="#{section_id}">{inline(title)}</a>'
                )
            index += 1
            continue

        if line.startswith("> "):
            flush_paragraph()
            close_list()
            quote_lines = []
            while index < len(lines) and lines[index].startswith("> "):
                quote_lines.append(lines[index][2:])
                index += 1
            out.append(f"<blockquote>{'<br>'.join(inline(item) for item in quote_lines)}</blockquote>")
            continue

        if re.match(r"^\|.*\|\s*$", line) and index + 1 < len(lines) and re.match(
            r"^\|[\s:|-]+\|\s*$", lines[index + 1]
        ):
            flush_paragraph()
            close_list()
            header_cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and re.match(r"^\|.*\|\s*$", lines[index]):
                rows.append([cell.strip() for cell in lines[index].strip().strip("|").split("|")])
                index += 1
            table = ["<div class=\"table-wrap\"><table><thead><tr>"]
            table.extend(f"<th>{inline(cell)}</th>" for cell in header_cells)
            table.append("</tr></thead><tbody>")
            for row in rows:
                table.append("<tr>")
                table.extend(f"<td>{inline(cell)}</td>" for cell in row)
                table.append("</tr>")
            table.append("</tbody></table></div>")
            out.append("".join(table))
            continue

        bullet = re.match(r"^\s*[-*]\s+(.+)$", line)
        ordered = re.match(r"^\s*\d+\.\s+(.+)$", line)
        if bullet or ordered:
            flush_paragraph()
            wanted = "ul" if bullet else "ol"
            if list_kind != wanted:
                close_list()
                list_kind = wanted
                out.append(f"<{wanted}>")
            out.append(f"<li>{inline((bullet or ordered).group(1))}</li>")
            index += 1
            continue

        if line.strip() == "---":
            flush_paragraph()
            close_list()
            out.append("<hr>")
            index += 1
            continue

        if line.startswith("**"):
            flush_paragraph()
            close_list()
            out.append(f"<p>{inline(line)}</p>")
            index += 1
            continue

        if not line.strip():
            flush_paragraph()
            close_list()
        else:
            paragraph.append(line.strip())
        index += 1

    flush_paragraph()
    close_list()
    if in_code:
        out.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(out), "\n".join(toc)


def page(body: str, toc: str, locale: dict[str, str]) -> str:
    download_file = locale["source"]
    current = locale["lang"]
    detector = ""
    if current == "zh-Hant":
        detector = """<script>
(function () {
  var key = "identityservice-docs-language";
  var saved = null;
  try { saved = localStorage.getItem(key); } catch (_) {}
  var languages = saved ? [saved] : (navigator.languages || [navigator.language || ""]);
  var selected = "en";
  for (var i = 0; i < languages.length; i += 1) {
    var language = String(languages[i] || "").toLowerCase();
    if (/^zh-(hans|cn|sg|my)/.test(language)) { selected = "zh-Hans"; break; }
    if (/^zh-(hant|tw|hk|mo)/.test(language) || language === "zh") { selected = "zh-Hant"; break; }
    if (/^en(?:-|$)/.test(language)) { selected = "en"; break; }
  }
  var target = selected === "zh-Hans" ? "api.zh-Hans.html" : selected === "en" ? "api.en.html" : "";
  if (target) location.replace(target + location.search + location.hash);
})();
</script>"""
    language_links = []
    for lang, href, label in (
        ("zh-Hant", "api.html", "繁體中文"),
        ("zh-Hans", "api.zh-Hans.html", "简体中文"),
        ("en", "api.en.html", "English"),
    ):
        active = ' aria-current="page"' if lang == current else ""
        language_links.append(
            f'<a href="{href}" hreflang="{lang}" data-locale="{lang}"{active}>{label}</a>'
        )
    language_switcher = "".join(language_links)
    return f"""<!doctype html>
<html lang="{locale['lang']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{locale['description']}">
<link rel="alternate" hreflang="zh-Hant" href="api.html">
<link rel="alternate" hreflang="zh-Hans" href="api.zh-Hans.html">
<link rel="alternate" hreflang="en" href="api.en.html">
<link rel="alternate" hreflang="x-default" href="api.html">
<title>{locale['title']}</title>
{detector}
<style>
:root{{--bg:#07101f;--panel:#0d192d;--panel2:#111f36;--ink:#edf4ff;--muted:#9db0ca;--brand:#62d4ff;--accent:#8c7bff;--line:#263a57;--ok:#3ddc97;--post:#b79aff;--get:#62d4ff;--patch:#ffbf69}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:linear-gradient(135deg,#07101f,#0a1325 60%,#10162b);color:var(--ink);font:15px/1.72 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
a{{color:var(--brand);text-decoration:none}}a:hover{{text-decoration:underline}}code{{font-family:"SFMono-Regular",Consolas,monospace}}
.top{{position:sticky;top:0;z-index:20;display:flex;justify-content:space-between;align-items:center;padding:13px 24px;background:rgba(7,16,31,.92);border-bottom:1px solid var(--line);backdrop-filter:blur(12px)}}.brand{{font-weight:800;color:var(--ink)}}.brand span{{color:var(--brand)}}.top nav{{display:flex;gap:18px;align-items:center;flex-wrap:wrap;justify-content:flex-end}}.download{{padding:8px 13px;border:1px solid var(--brand);border-radius:9px}}.language{{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden}}.language a{{padding:5px 8px;color:var(--muted);font-size:.82rem}}.language a[aria-current="page"]{{background:var(--brand);color:#06101d;text-decoration:none}}
.layout{{max-width:1440px;margin:auto;display:grid;grid-template-columns:290px minmax(0,920px);gap:36px;padding:34px 28px 80px;justify-content:center}}
.toc{{position:sticky;top:86px;height:calc(100vh - 110px);overflow:auto;padding:12px 18px 24px;border-right:1px solid var(--line)}}.toc h2{{font-size:.8rem;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}}.toc a{{display:block;color:var(--muted);padding:5px 0;line-height:1.35}}.toc a:hover{{color:var(--brand)}}.toc-l3{{padding-left:14px!important;font-size:.86rem}}
main{{min-width:0}}h1{{font-size:clamp(2.1rem,5vw,3.8rem);line-height:1.08;margin:10px 0 26px;background:linear-gradient(90deg,#fff,var(--brand));-webkit-background-clip:text;color:transparent}}h2{{font-size:1.75rem;margin:64px 0 20px;padding-top:18px;border-top:1px solid var(--line)}}h3{{font-size:1.12rem;margin:38px 0 15px;padding:14px 17px;background:var(--panel2);border:1px solid var(--line);border-left:4px solid var(--brand);border-radius:10px}}h4{{margin:26px 0 8px;color:var(--brand)}}p,li{{color:#d4e0ef}}blockquote{{margin:20px 0;padding:15px 18px;background:rgba(98,212,255,.08);border-left:4px solid var(--brand);border-radius:7px;color:#dcecff}}hr{{border:0;border-top:1px solid var(--line);margin:36px 0}}
pre{{overflow:auto;padding:18px;background:#030913;border:1px solid var(--line);border-radius:10px;color:#d8f3ff;box-shadow:0 12px 30px rgba(0,0,0,.18)}}p code,li code,td code,blockquote code{{padding:2px 6px;background:#162640;border:1px solid #294362;border-radius:5px;color:#aeeaff}}
.table-wrap{{overflow:auto;margin:14px 0 24px;border:1px solid var(--line);border-radius:10px}}table{{width:100%;border-collapse:collapse;background:var(--panel)}}th,td{{padding:11px 13px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}}th{{color:var(--brand);background:#12213a;white-space:nowrap}}tr:last-child td{{border-bottom:0}}
.endpoint-title code{{font-size:.95em;color:var(--ink)}}footer{{margin-top:60px;padding-top:20px;border-top:1px solid var(--line);color:var(--muted)}}@media(max-width:920px){{.top{{align-items:flex-start;gap:10px}}.top nav{{flex-wrap:wrap;justify-content:flex-end}}.layout{{display:block;padding:20px 16px 60px}}.toc{{position:relative;top:auto;height:auto;border:1px solid var(--line);border-radius:10px;margin-bottom:28px;max-height:360px}}h2{{margin-top:45px}}}}
</style>
</head>
<body>
<header class="top">
  <a class="brand" href="index.html">Identity<span>Service</span></a>
  <nav><a href="index.html">{locale['home']}</a><a href="{locale['quick_file']}">{locale['quick']}</a><span class="language" aria-label="Language">{language_switcher}</span><a class="download" href="{download_file}" download>{locale['download']}</a></nav>
</header>
<div class="layout">
  <aside class="toc" aria-label="API"><h2>{locale['toc']}</h2>{toc}</aside>
  <main>{body}<footer>{locale['footer']}</footer></main>
</div>
<script>
document.querySelectorAll("[data-locale]").forEach(function (link) {{
  link.addEventListener("click", function () {{
    try {{ localStorage.setItem("identityservice-docs-language", link.getAttribute("data-locale")); }} catch (_) {{}}
  }});
}});
</script>
</body>
</html>
"""


def main() -> None:
    for locale in LOCALES:
        source = ROOT / locale["source"]
        target = ROOT / locale["target"]
        body, toc = render_markdown(source.read_text(encoding="utf-8"))
        target.write_text(page(body, toc, locale), encoding="utf-8")


if __name__ == "__main__":
    main()
