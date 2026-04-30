"""Generate static HTML dashboard pages from summary JSON files."""

import json
import os
import re
from datetime import datetime, timezone, timedelta

EST = timezone(timedelta(hours=-5))


def slugify(name):
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug.strip("-")


def load_summaries(data_dir):
    summaries = []
    if not os.path.isdir(data_dir):
        return summaries
    for entry in sorted(os.listdir(data_dir)):
        summary_path = os.path.join(data_dir, entry, "summary.json")
        if os.path.isfile(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    s = json.load(f)
                s["_slug"] = entry
                summaries.append(s)
            except Exception as e:
                print(f"WARNING: Failed to load {summary_path}: {e}")
    return summaries


def format_est(iso_str):
    if not iso_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.astimezone(EST).strftime("%b %d, %Y %I:%M %p EST")
    except Exception:
        return iso_str


def format_date_short(iso_str):
    if not iso_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.astimezone(EST).strftime("%b %d")
    except Exception:
        return iso_str


STATUS_COLORS = {
    "Verified": "#22c55e",
    "Device Mounted": "#3b82f6",
    "Wire Roughed In": "#eab308",
    "Tested Failed": "#ef4444",
}


def status_color(status):
    return STATUS_COLORS.get(status.strip(), "#6b7280")


def generate_index(summaries, docs_dir):
    now_est = datetime.now(timezone.utc).astimezone(EST).strftime("%b %d, %Y %I:%M %p EST")

    cards_html = ""
    for s in summaries:
        slug = s["_slug"]
        # Use percent_touched for the ring; fall back to old percent_complete if missing
        pct_touched = s.get("percent_touched", s.get("percent_complete", 0))
        total = s.get("total_tasks", 0)
        touched = s.get("touched_tasks", s.get("completed_tasks", 0))
        completed = s.get("completed_tasks", 0)
        in_progress = s.get("in_progress_tasks", 0)
        not_started = s.get("not_started_tasks", 0)
        today_count = len(s.get("todays_activity", []))
        blocked_count = len(s.get("blocked_tasks", []))
        has_stale = s.get("has_stale_floors", False)

        circumference = 2 * 3.14159 * 40
        offset = circumference - (pct_touched / 100) * circumference

        badges = ""
        if has_stale:
            badges += '<span class="badge badge-red">Inactive Floor</span>'
        if blocked_count > 0:
            badges += f'<span class="badge badge-yellow">{blocked_count} Blocked</span>'

        cards_html += f"""
        <div class="card">
          <h3>{s.get("project_name", slug)}</h3>
          <div class="progress-ring-wrap">
            <svg width="100" height="100" viewBox="0 0 100 100">
              <circle cx="50" cy="50" r="40" fill="none" stroke="#2a2d3a" stroke-width="8"/>
              <circle cx="50" cy="50" r="40" fill="none" stroke="#818cf8" stroke-width="8"
                stroke-dasharray="{circumference}" stroke-dashoffset="{offset}"
                stroke-linecap="round" transform="rotate(-90 50 50)"/>
            </svg>
            <span class="pct-label">{pct_touched:.0f}%</span>
          </div>
          <p class="tasks-count">{touched}/{total} tasks in progress</p>
          <p class="detail-text">{completed} completed &middot; {in_progress} in progress &middot; {not_started} not started</p>
          <p class="today-count">{today_count} task{"s" if today_count != 1 else ""} updated today</p>
          <div class="badges">{badges}</div>
          <a href="project-{slug}.html" class="btn">View Dashboard</a>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Younitech Dashboard</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #111318; color: #d8dae5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; min-height: 100vh; }}
  .header {{ background: #1a1d27; padding: 24px 32px; border-bottom: 1px solid #2a2d3a; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
  .header h1 {{ color: #818cf8; font-size: 24px; }}
  .header .sync {{ color: #6b7280; font-size: 13px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 24px; padding: 32px; max-width: 1400px; margin: 0 auto; }}
  .card {{ background: #1a1d27; border-radius: 12px; padding: 28px; border: 1px solid #2a2d3a; display: flex; flex-direction: column; align-items: center; gap: 8px; }}
  .card h3 {{ color: #e2e4ed; font-size: 18px; text-align: center; }}
  .progress-ring-wrap {{ position: relative; width: 100px; height: 100px; }}
  .pct-label {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 20px; font-weight: 700; color: #818cf8; }}
  .tasks-count {{ color: #9ca3af; font-size: 14px; }}
  .detail-text {{ color: #6b7280; font-size: 12px; text-align: center; }}
  .today-count {{ color: #6b7280; font-size: 13px; }}
  .badges {{ display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; min-height: 28px; }}
  .badge {{ padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; }}
  .badge-red {{ background: #7f1d1d; color: #fca5a5; }}
  .badge-yellow {{ background: #713f12; color: #fde68a; }}
  .btn {{ display: inline-block; margin-top: 8px; padding: 10px 20px; background: #818cf8; color: #111318; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14px; transition: background 0.2s; }}
  .btn:hover {{ background: #6366f1; }}
  .footer {{ text-align: center; padding: 24px; color: #4b5563; font-size: 13px; }}
  .empty {{ text-align: center; padding: 80px 32px; color: #6b7280; }}
</style>
</head>
<body>
<div class="header">
  <h1>Younitech Dashboard</h1>
  <span class="sync">Last synced: {now_est}</span>
</div>
{"<div class='empty'><p>No projects found yet. Reports will appear here after the first email sync.</p></div>" if not summaries else ""}
<div class="grid">{cards_html}</div>
<div class="footer">Last synced: {now_est}</div>
</body>
</html>"""

    index_path = os.path.join(docs_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated {index_path}")


def generate_project_page(summary, docs_dir):
    slug = summary["_slug"]
    project_name = summary.get("project_name", slug)
    now_est = datetime.now(timezone.utc).astimezone(EST).strftime("%b %d, %Y %I:%M %p EST")

    # -- Overview stats --
    touched = summary.get("touched_tasks", summary.get("completed_tasks", 0))
    total = summary.get("total_tasks", 0)
    completed = summary.get("completed_tasks", 0)
    in_progress = summary.get("in_progress_tasks", 0)
    not_started = summary.get("not_started_tasks", 0)

    overview_html = f"""
    <section class="section overview">
      <div class="stats-grid">
        <div class="stat"><span class="stat-num">{touched}/{total}</span> <span>touched</span></div>
        <div class="stat"><span class="stat-num">{completed}</span> <span>completed</span></div>
        <div class="stat"><span class="stat-num">{in_progress}</span> <span>in progress</span></div>
        <div class="stat"><span class="stat-num">{not_started}</span> <span>not started</span></div>
      </div>
    </section>"""

    # Today's Activity
    activity_html = ""
    todays = summary.get("todays_activity", [])
    if todays:
        rows = ""
        for item in todays:
            color = status_color(item.get("status", ""))
            rows += f"""
            <div class="activity-row">
              <span class="status-dot" style="background:{color}"></span>
              <span class="activity-name">{item.get("task_name","")}</span>
              <span class="activity-badge" style="background:{color}22;color:{color}">{item.get("status","")}</span>
              <span class="activity-meta">{item.get("location","")}</span>
              <span class="activity-meta">{item.get("assignee","")}</span>
            </div>"""
        activity_html = f"""
        <section class="section">
          <h2>Today's Activity</h2>
          <div class="activity-feed">{rows}</div>
        </section>"""
    else:
        activity_html = """
        <section class="section">
          <h2>Today's Activity</h2>
          <p class="muted">No activity recorded today.</p>
        </section>"""

    # Floor Progress (now includes touched bar and breakdown)
    floor_rows = ""
    for fl in summary.get("floors", []):
        pct_touched = fl.get("percent_touched", fl.get("percent_complete", 0))
        total = fl.get("total_tasks", 0)
        completed = fl.get("completed_tasks", 0)
        in_progress = fl.get("in_progress_tasks", 0)
        not_started = fl.get("not_started_tasks", 0)
        last_act = format_date_short(fl.get("last_activity"))
        stale_badge = '<span class="badge badge-red">STALE 7d+</span>' if fl.get("is_stale") else ""
        floor_rows += f"""
        <tr>
          <td>{fl.get("name","")}</td>
          <td>
            <div class="bar-wrap">
              <div class="bar-fill" style="width:{pct_touched}%"></div>
            </div>
          </td>
          <td>{completed}/{total}</td>
          <td>{pct_touched:.0f}%</td>
          <td>{last_act}</td>
          <td>{stale_badge}</td>
        </tr>"""

    floor_html = f"""
    <section class="section">
      <h2>Floor Progress</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Floor</th><th>Progress</th><th>Status</th><th>% Touched</th><th>Last Activity</th><th></th></tr></thead>
          <tbody>{floor_rows}</tbody>
        </table>
      </div>
    </section>"""

    # Blocked Tasks
    blocked = summary.get("blocked_tasks", [])
    blocked_html = ""
    if blocked:
        items = ""
        for b in blocked:
            items += f"""
            <div class="blocked-item">
              <strong>{b.get("task_name","")}</strong>
              <span>{b.get("location","")}</span>
              <span>{b.get("assignee","")}</span>
            </div>"""
        blocked_html = f"""
        <section class="section">
          <h2>Blocked Tasks</h2>
          <div class="blocked-panel">{items}</div>
        </section>"""

    # Category Breakdown
    cats = summary.get("category_breakdown", {})
    cat_rows = ""
    for cat_name, count in sorted(cats.items(), key=lambda x: -x[1]):
        cat_rows += f'<div class="cat-row"><span>{cat_name}</span><span>{count}</span></div>'
    cat_html = f"""
    <section class="section">
      <h2>Category Breakdown</h2>
      <div class="cat-list">{cat_rows}</div>
    </section>""" if cats else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{project_name} — Younitech Dashboard</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #111318; color: #d8dae5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; min-height: 100vh; }}
  .header {{ background: #1a1d27; padding: 20px 32px; border-bottom: 1px solid #2a2d3a; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
  .header h1 {{ color: #818cf8; font-size: 22px; }}
  .header a {{ color: #818cf8; text-decoration: none; font-size: 14px; }}
  .header a:hover {{ text-decoration: underline; }}
  .content {{ max-width: 1100px; margin: 0 auto; padding: 24px 32px; }}
  .section {{ background: #1a1d27; border-radius: 12px; padding: 24px; border: 1px solid #2a2d3a; margin-bottom: 24px; }}
  .section h2 {{ color: #818cf8; font-size: 17px; margin-bottom: 16px; }}
  .muted {{ color: #6b7280; font-size: 14px; }}
  .overview .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 16px; }}
  .stat {{ background: #111318; border-radius: 8px; padding: 12px; text-align: center; }}
  .stat-num {{ display: block; font-size: 24px; font-weight: 700; color: #818cf8; }}
  .stat span:last-child {{ color: #6b7280; font-size: 13px; }}
  .activity-feed {{ display: flex; flex-direction: column; gap: 8px; }}
  .activity-row {{ display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: #111318; border-radius: 8px; flex-wrap: wrap; }}
  .status-dot {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
  .activity-name {{ font-weight: 600; flex: 1; min-width: 150px; }}
  .activity-badge {{ padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }}
  .activity-meta {{ color: #6b7280; font-size: 13px; }}
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #2a2d3a; font-size: 14px; white-space: nowrap; }}
  th {{ color: #9ca3af; font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .bar-wrap {{ width: 120px; height: 8px; background: #2a2d3a; border-radius: 4px; overflow: hidden; }}
  .bar-fill {{ height: 100%; background: #818cf8; border-radius: 4px; transition: width 0.3s; }}
  .badge {{ padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; }}
  .badge-red {{ background: #7f1d1d; color: #fca5a5; }}
  .blocked-panel {{ background: #2a1215; border: 1px solid #7f1d1d; border-radius: 8px; padding: 16px; display: flex; flex-direction: column; gap: 10px; }}
  .blocked-item {{ display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }}
  .blocked-item strong {{ color: #fca5a5; }}
  .blocked-item span {{ color: #9ca3af; font-size: 13px; }}
  .cat-list {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }}
  .cat-row {{ display: flex; justify-content: space-between; padding: 8px 14px; background: #111318; border-radius: 6px; font-size: 14px; }}
  .iframe-wrap {{ margin-top: 24px; border-radius: 12px; overflow: hidden; border: 1px solid #2a2d3a; }}
  .iframe-wrap iframe {{ width: 100%; height: 800px; border: none; }}
  .footer {{ text-align: center; padding: 24px; color: #4b5563; font-size: 13px; }}
</style>
</head>
<body>
<div class="header">
  <div>
    <a href="index.html">&larr; Back to Projects</a>
    <h1>{project_name}</h1>
  </div>
  <span style="color:#6b7280;font-size:13px">Updated: {now_est}</span>
</div>
<div class="content">
  {overview_html}
  {activity_html}
  {floor_html}
  {blocked_html}
  {cat_html}
  <div class="iframe-wrap">
    <iframe src="dashboard.html" title="Interactive Dashboard"></iframe>
  </div>
</div>
<div class="footer">Last synced: {now_est}</div>
</body>
</html>"""

    page_path = os.path.join(docs_dir, f"project-{slug}.html")
    with open(page_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated {page_path}")


def generate_site(data_dir, docs_dir):
    os.makedirs(docs_dir, exist_ok=True)
    summaries = load_summaries(data_dir)
    print(f"Found {len(summaries)} project(s) to render.")

    generate_index(summaries, docs_dir)

    for s in summaries:
        try:
            generate_project_page(s, docs_dir)
        except Exception as e:
            print(f"ERROR: Failed to generate page for {s.get('project_name','?')}: {e}")

    print("Site generation complete.")


if __name__ == "__main__":
    base = os.path.dirname(os.path.dirname(__file__))
    generate_site(
        os.path.join(base, "data"),
        os.path.join(base, "docs"),
    )
