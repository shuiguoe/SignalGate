from __future__ import annotations

import os
import urllib.parse
import urllib.request


DEFAULT_URL = "https://api2.pushdeer.com/message/push"


def send_push(text: str, desp: str = "", pushkey: str | None = None, url: str | None = None) -> bool:
    """
    PushDeer v0.1
    - 仅负责发送推送
    - 参数遵循官方：POST /message/push {pushkey,text,desp,type}  :contentReference[oaicite:2]{index=2}
    """
    pk = (pushkey or os.getenv("PUSHDEER_KEY") or "").strip()
    if not pk:
        raise RuntimeError("Missing PUSHDEER_KEY (set env or pass --pushkey).")

    endpoint = (url or os.getenv("PUSHDEER_URL") or DEFAULT_URL).strip()

    data = {
        "pushkey": pk,
        "text": text,
        "desp": desp,
        "type": "text",
    }
    body = urllib.parse.urlencode(data).encode("utf-8")

    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=15) as resp:
        # PushDeer 在线版通常返回 JSON，但 v0.1 不依赖返回结构（只要 HTTP 200）
        return 200 <= int(resp.status) < 300
