"""统一 HTTP 会话工具：自适应网络请求（直连优先，失败自动切换系统代理）。

背景：本机网络两个坑——
1. 用户级代理指向 127.0.0.1:10090，有时无服务监听（连接拒绝）；
2. 开着代理软件时，直连部分境外 API（api.github.com / apihub.agnes-ai.com）
   偶发 SSL 被掐断/连接超时（间歇性干扰）。
因此所有外部请求统一走 adaptive_request：直连失败自动重试并回退系统代理，
两种网络状态下都能自愈。单次简单请求仍可用 direct_session()。
"""
import time

import requests


def direct_session() -> requests.Session:
    """返回一个忽略系统代理的 requests.Session（每次新建，线程安全）"""
    s = requests.Session()
    s.trust_env = False  # 忽略环境变量与 Windows 注册表代理
    return s


# 网络模式（设置页可切换）：auto=直连优先失败换代理 / direct=仅直连 / proxy=仅系统代理
_MODE_ATTEMPTS = {
    "auto": (False, True),
    "direct": (False,),
    "proxy": (True,),
}
_network_mode = "auto"


def set_network_mode(mode: str):
    """设置全局网络模式（设置页调用；未知值回退 auto）"""
    global _network_mode
    _network_mode = mode if mode in _MODE_ATTEMPTS else "auto"


def _rewind_files(files):
    """重试前把 multipart 文件指针归零（否则第二次尝试会发空内容）"""
    if not files:
        return
    for v in files.values():
        for part in (v if isinstance(v, tuple) else (v,)):
            if hasattr(part, "seek"):
                try:
                    part.seek(0)
                except Exception:
                    pass


def adaptive_request(method: str, url: str, *, headers=None, json=None,
                     data=None, files=None, params=None, timeout=30,
                     attempts=None, backoff: float = 1.0):
    """自适应请求：attempts 为 None 时按全局网络模式决定尝试顺序。
    仅对连接类异常（超时/SSL/代理拒绝）换道重试；HTTP 状态码原样返回不重试。"""
    if attempts is None:
        attempts = _MODE_ATTEMPTS[_network_mode]
    last_exc = None
    for i, trust_env in enumerate(attempts):
        s = requests.Session()
        s.trust_env = trust_env
        try:
            return s.request(method, url, headers=headers, json=json,
                             data=data, files=files, params=params,
                             timeout=timeout)
        except requests.RequestException as e:
            last_exc = e
            if i < len(attempts) - 1:
                _rewind_files(files)
                time.sleep(backoff * (i + 1))
    raise last_exc
