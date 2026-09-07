"""
图床上传模块：本地图片 → 可公开访问的直链
供视频生成使用（视频接口仅支持公网 URL，不支持本地文件/base64）。

支持两个提供方（自动选择，见 upload_to_image_host）：
1. GitHub 仓库（免费推荐）：
   - 需 .env 配置 GITHUB_TOKEN + GITHUB_REPO（公开仓库）
   - 走 Contents API 上传，raw.githubusercontent.com 直链
2. S.EE（原 SM.MS 团队，2026-08 起付费方案 $5.99/月起）：
   - 需 .env 配置 SEE_API_TOKEN（兼容旧 SMMS_API_TOKEN）
   - POST https://s.ee/api/v1/file/upload（multipart 字段 file，鉴权裸 key）
"""
import base64
import os
import time
import urllib.parse

import requests

from dotenv import load_dotenv

from http_session import adaptive_request

try:
    from agens_core import resource_path, runtime_dir
except Exception:  # 独立使用时兜底
    def resource_path(p):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), p)

    def runtime_dir():
        return os.path.dirname(os.path.abspath(__file__))

_SEE_UPLOAD_URL = "https://s.ee/api/v1/file/upload"
_GH_API = "https://api.github.com"
_MAX_MB = 5  # 保守上限


def _gh_api_call(method: str, url: str, headers: dict, *,
                 json_body=None, timeout: int = 60):
    """GitHub API 调用（抗网络抖动）：直连重试×2，仍失败回退系统代理。
    背景：本机到 api.github.com 偶发 SSL 被掐断（间歇性干扰），重试/换道即可恢复。"""
    return adaptive_request(method, url, headers=headers, json=json_body,
                            timeout=timeout, attempts=(False, False, True),
                            backoff=1.5)


def _load_env():
    # 运行时 .env（exe 目录）优先，内置 .env 兜底
    load_dotenv(os.path.join(runtime_dir(), ".env"))
    load_dotenv(resource_path(".env"))
    load_dotenv()


def _get(name: str) -> str:
    return (os.environ.get(name) or "").strip()


# ---------- GitHub 仓库图床（免费） ----------

GH_GUIDE = (
    "GitHub 图床尚未配置。开通步骤（免费，约 5 分钟）：\n"
    "  1. GitHub 新建一个【公开】仓库，如 my-images\n"
    "  2. 右上角头像 → Settings → Developer settings →\n"
    "     Personal access tokens → Generate new token：\n"
    "     · 经典 token：勾选 repo 权限；或\n"
    "     · Fine-grained：仅选中该仓库，Contents 权限选 Read and write\n"
    "  3. 用记事本打开软件目录下的 .env，加两行：\n"
    "     GITHUB_TOKEN=你的token\n"
    "     GITHUB_REPO=你的用户名/my-images\n"
    "  4. 重启软件，再选本地文件即可自动上传\n"
)


def upload_to_github(path: str, token: str = None, repo: str = None,
                     branch: str = None, timeout: int = 60) -> str:
    """
    上传本地图片到 GitHub 公开仓库，返回 raw 直链。
    :raises ValueError: 未配置/文件过大/不存在
    :raises Exception: API 报错
    """
    if not path or not os.path.isfile(path):
        raise ValueError(f"文件不存在: {path}")
    size_mb = os.path.getsize(path) / (1024 * 1024)
    if size_mb > _MAX_MB:
        raise ValueError(f"图片超过 {_MAX_MB}MB（当前 {size_mb:.1f}MB），请压缩后再试")

    _load_env()
    token = (token or _get("GITHUB_TOKEN"))
    repo = (repo or _get("GITHUB_REPO"))
    if not token or not repo:
        raise ValueError(GH_GUIDE)
    repo = repo.strip().strip("/")
    branch = (branch or _get("GITHUB_BRANCH") or "").strip()

    headers = {
        "User-Agent": "AgnesGenerator/1.0",
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # 未指定分支时取仓库默认分支（避免 main/master 猜错）
    if not branch:
        r = _gh_api_call("GET", f"{_GH_API}/repos/{repo}", headers, timeout=timeout)
        if r.status_code == 401:
            raise ValueError("GITHUB_TOKEN 无效或已过期，请重新生成。\n" + GH_GUIDE)
        if r.status_code == 404:
            raise ValueError(f"仓库 {repo} 不存在或 token 无权访问，请检查 GITHUB_REPO。\n" + GH_GUIDE)
        r.raise_for_status()
        branch = r.json().get("default_branch") or "main"

    with open(path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode("ascii")
    basename = os.path.basename(path)
    # 时间戳前缀防重名（同秒重复上传也能区分）
    repo_path = f"agnes-refs/{int(time.time() * 1000)}_{basename}"

    body = {
        "message": f"upload reference image {basename}",
        "content": content_b64,
        "branch": branch,
    }
    r = _gh_api_call("PUT",
                     f"{_GH_API}/repos/{repo}/contents/{urllib.parse.quote(repo_path)}",
                     headers, json_body=body, timeout=timeout)
    if r.status_code in (401, 403):
        raise ValueError("GITHUB_TOKEN 无效或权限不足（需要 repo/Contents 写权限）。\n" + GH_GUIDE)
    if r.status_code == 404:
        raise ValueError(f"仓库 {repo} 不存在，或分支 {branch} 不存在。\n" + GH_GUIDE)
    if r.status_code not in (200, 201):
        try:
            msg = r.json().get("message", "")
        except Exception:
            msg = r.text[:150]
        raise Exception(f"GitHub 上传失败(HTTP {r.status_code}): {msg}")

    data = r.json().get("content") or {}
    url = data.get("download_url")
    if not url:
        url = (f"https://raw.githubusercontent.com/{repo}/{branch}/"
               + urllib.parse.quote(repo_path))
    return url


# ---------- S.EE 图床（付费方案） ----------

SEE_GUIDE = (
    "S.EE 图床（原 SM.MS）自 2026-08 起需付费方案（$5.99/月起）。\n"
    "推荐改用免费的 GitHub 图床（见下方 GitHub 配置指引）。\n"
    "如仍想用 S.EE：登录 https://s.ee → 用户中心生成 API Key →\n"
    ".env 加一行 SEE_API_TOKEN=你的Key"
)


def upload_to_see(path: str, token: str = None, timeout: int = 120) -> str:
    """上传本地图片到 S.EE，返回直链（需 SEE_API_TOKEN，付费）"""
    if not path or not os.path.isfile(path):
        raise ValueError(f"文件不存在: {path}")
    size_mb = os.path.getsize(path) / (1024 * 1024)
    if size_mb > _MAX_MB:
        raise ValueError(f"图片超过 {_MAX_MB}MB（当前 {size_mb:.1f}MB），请压缩后再试")

    _load_env()
    token = (token or _get("SEE_API_TOKEN") or _get("SMMS_API_TOKEN")).strip()
    if not token:
        raise ValueError(SEE_GUIDE)

    headers = {"User-Agent": "AgnesGenerator/1.0", "Authorization": token}
    try:
        with open(path, "rb") as f:
            resp = adaptive_request(
                "POST", _SEE_UPLOAD_URL, files={"file": f},
                headers=headers, timeout=timeout,
            )
    except Exception as e:
        raise Exception(f"图床上传失败: {type(e).__name__}: {e}") from e

    if resp.status_code in (401, 403):
        raise ValueError("S.EE API Key 无效、过期或当前方案无上传权限。\n" + SEE_GUIDE)
    try:
        data = resp.json()
    except Exception:
        raise Exception(f"图床上传失败(HTTP {resp.status_code}): {resp.text[:150]}")

    if isinstance(data, dict):
        payload = data.get("data")
        url = payload.get("url") if isinstance(payload, dict) else None
        if url:
            return url
        images = data.get("images")
        if isinstance(images, list) and images:
            return images[0]
        if isinstance(images, str) and images:
            return images
        raise Exception(f"图床上传失败: {data.get('message') or str(data)[:150]}")
    raise Exception(f"图床上传失败: 无法解析响应 {str(data)[:150]}")


# ---------- 自动路由 ----------

def upload_to_image_host(path: str, provider: str = None) -> str:
    """
    本地图片 → 公网直链（自动选择提供方）：
    - provider="see"/"github" 时用指定方；
    - 缺省 auto：配了 SEE_API_TOKEN 用 S.EE，否则配了 GITHUB_TOKEN+GITHUB_REPO 用 GitHub；
    - 都未配置时抛出合并指引。
    """
    _load_env()
    provider = (provider or "auto").lower()
    if provider == "see":
        return upload_to_see(path)
    if provider == "github":
        return upload_to_github(path)

    see_ready = bool(_get("SEE_API_TOKEN") or _get("SMMS_API_TOKEN"))
    gh_ready = bool(_get("GITHUB_TOKEN") and _get("GITHUB_REPO"))
    if see_ready:
        return upload_to_see(path)
    if gh_ready:
        return upload_to_github(path)
    raise ValueError(
        "尚未配置图床（二选一，推荐免费的 GitHub 方案）：\n\n"
        + GH_GUIDE + "\n" + SEE_GUIDE
    )
