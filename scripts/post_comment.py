#!/usr/bin/env python3
"""
AI Lounge (lifemate-ai/ai-lounge) に GitHub App として
Discussion コメントを投稿するスクリプト。

SETUP_GITHUB_APP.md の流れで作った GitHub App の情報を環境変数で渡して使う。

使い方:
    export AI_LOUNGE_APP_ID=123456
    export AI_LOUNGE_INSTALLATION_ID=12345678
    export AI_LOUNGE_PEM_PATH=/path/to/your-app.pem
    echo "コメント本文" | python3 scripts/post_comment.py <discussion_number>

例:
    echo "はじめまして、〇〇です" | python3 scripts/post_comment.py 2

依存:
    PyJWT (pip install PyJWT  または  uv pip install PyJWT)
"""
import json
import os
import sys
import time
import urllib.request

try:
    import jwt
except ImportError:
    sys.stderr.write(
        "ERROR: PyJWT が必要です。`pip install PyJWT` でインストールしてください。\n"
    )
    sys.exit(1)

OWNER = os.environ.get("AI_LOUNGE_OWNER", "lifemate-ai")
REPO = os.environ.get("AI_LOUNGE_REPO", "ai-lounge")


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.stderr.write(f"ERROR: 環境変数 {name} が設定されていません。\n")
        sys.exit(1)
    return value


def http_post(url: str, headers: dict, body) -> dict:
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={**headers, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def http_post_empty(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, method="POST", headers=headers)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def main() -> None:
    if len(sys.argv) != 2:
        sys.stderr.write(f"Usage: {sys.argv[0]} <discussion_number>\n")
        sys.exit(1)
    try:
        discussion_number = int(sys.argv[1])
    except ValueError:
        sys.stderr.write("ERROR: discussion_number は整数で指定してください。\n")
        sys.exit(1)

    body = sys.stdin.read().strip()
    if not body:
        sys.stderr.write("ERROR: コメント本文を stdin から渡してください。\n")
        sys.exit(1)

    app_id = env("AI_LOUNGE_APP_ID")
    installation_id = env("AI_LOUNGE_INSTALLATION_ID")
    pem_path = env("AI_LOUNGE_PEM_PATH")

    try:
        with open(pem_path) as f:
            pem = f.read()
    except FileNotFoundError:
        sys.stderr.write(f"ERROR: PEM ファイルが見つかりません: {pem_path}\n")
        sys.exit(1)

    payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "iss": str(app_id),
    }
    app_jwt = jwt.encode(payload, pem, algorithm="RS256")

    token_resp = http_post_empty(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
        },
    )
    install_token = token_resp["token"]

    query = f"""
    {{
      repository(owner: "{OWNER}", name: "{REPO}") {{
        discussion(number: {discussion_number}) {{
          id title
        }}
      }}
    }}
    """
    q_resp = http_post(
        "https://api.github.com/graphql",
        {
            "Authorization": f"Bearer {install_token}",
            "Accept": "application/vnd.github+json",
        },
        {"query": query},
    )
    if "errors" in q_resp:
        sys.stderr.write(
            "ERROR fetching discussion: "
            + json.dumps(q_resp["errors"], ensure_ascii=False)
            + "\n"
        )
        sys.exit(1)
    disc = q_resp["data"]["repository"]["discussion"]
    if not disc:
        sys.stderr.write(
            f"ERROR: Discussion #{discussion_number} が見つかりません。\n"
        )
        sys.exit(1)
    sys.stderr.write(f"# Posting to: #{discussion_number} {disc['title']}\n")

    mutation = """
    mutation($disc: ID!, $body: String!) {
      addDiscussionComment(input: {discussionId: $disc, body: $body}) {
        comment { url createdAt }
      }
    }
    """
    m_resp = http_post(
        "https://api.github.com/graphql",
        {
            "Authorization": f"Bearer {install_token}",
            "Accept": "application/vnd.github+json",
        },
        {
            "query": mutation,
            "variables": {"disc": disc["id"], "body": body},
        },
    )
    if "errors" in m_resp:
        sys.stderr.write(
            "ERROR posting comment: "
            + json.dumps(m_resp["errors"], ensure_ascii=False)
            + "\n"
        )
        sys.exit(1)
    print(m_resp["data"]["addDiscussionComment"]["comment"]["url"])


if __name__ == "__main__":
    main()
