"""
在你的 API 服务器上使用：调用 GitHub API 触发 Manim 渲染 workflow

使用方式:
    from trigger_render import trigger_manim_render
    result = trigger_manim_render(
        cos_scene_url="https://xxx.cos.ap-beijing.myqcloud.com/scene.py",
        scene_class="MyScene",
        callback_url="https://你的服务器/api/manim_callback",
        task_id="task_123"
    )
"""

import os
import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "ghp_xxxxxxxx")
REPO_OWNER = "weiylhappy"
REPO_NAME = "manim-render"
WORKFLOW_ID = "render.yml"

API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows/{WORKFLOW_ID}/dispatches"


def trigger_manim_render(
    cos_scene_url: str,
    scene_class: str = "MyScene",
    callback_url: str = "",
    task_id: str = "",
) -> dict:
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    payload = {
        "ref": "main",
        "inputs": {
            "cos_scene_url": cos_scene_url,
            "scene_class": scene_class,
            "callback_url": callback_url,
            "task_id": task_id,
        },
    }

    try:
        resp = requests.post(API_BASE, headers=headers, json=payload, timeout=30)
        if resp.status_code == 204:
            return {"ok": True}
        else:
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text}"}
    except requests.RequestException as e:
        return {"ok": False, "error": str(e)}


def get_latest_run_status() -> dict:
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    resp = requests.get(url, headers=headers, params={"per_page": 1})
    if resp.status_code != 200:
        return {"ok": False, "error": resp.text}

    runs = resp.json().get("workflow_runs", [])
    if not runs:
        return {"ok": True, "status": "no_runs"}

    run = runs[0]
    return {
        "ok": True,
        "run_id": run["id"],
        "status": run["status"],
        "conclusion": run["conclusion"],
        "url": run["html_url"],
    }
