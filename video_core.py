"""
Agnes 视频生成核心模块
集成：文生视频（text）、图片参考视频（reference）
"""
import os
import sys
import time
import requests
from dotenv import load_dotenv

from http_session import adaptive_request

# 视频查询端点（固定地址，与 images 不同）
VIDEO_QUERY_URL = "https://apihub.agnes-ai.com/agnesapi"

# 完成状态集合
DONE_STATUSES = {"completed", "succeeded", "success", "failed", "error", "canceled", "cancelled"}
FAILED_STATUSES = {"failed", "error", "canceled", "cancelled"}

# 支持的画幅（对应输出像素均为 720P 基准）
ASPECT_RATIOS = ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"]

# 支持的时长（秒，字符串格式）
SECONDS_OPTIONS = ["4", "5", "8", "10", "12"]

# 可用视频模型（agnes-video-2.5-flash 为新增：限时免费，官方文档
# https://www.agnes-ai.com/zh-Hans/docs/agnes-video-25-flash）
VIDEO_MODELS = ["agnes-video-2.5-flash", "agnes-video-2.5", "agnes-video-v2.0"]

# Flash 系模型查询限制：不带 model_name 的纯 video_id 查询仅适用于 mode=text，
# reference / keyframe 模式必须附带 model_name 才能查询到任务
FLASH_VIDEO_MODELS = {"agnes-video-2.5-flash"}


class VideoQueueFullError(Exception):
    """服务端视频队列满（HTTP 503 video_queue_full），可稍后重试"""


class VideoRateLimitError(Exception):
    """触发速率限制（HTTP 429 rate_limit_exceeded，视频每分钟仅允许 1 个任务），可稍后重试"""


# 可自动重试的临时故障集合
RETRYABLE_VIDEO_ERRORS = (VideoQueueFullError, VideoRateLimitError)


def validate_video_images(images) -> None:
    """校验视频参考图：仅接受可公开访问的 http(s) URL。
    实测（2026-08-25）：文档约定 images 为「URL 列表」；接口虽在报错里提到
    base64，但裸 base64 与 data URI 两种正确编码均被 400 拒绝，base64 通道
    未实现/已损坏。本地文件请先上传图床，或使用图片生成页（支持本地文件）。"""
    for x in images or []:
        s = str(x).strip()
        if s and not s.lower().startswith(("http://", "https://")):
            raise ValueError(
                "视频参考图仅支持可公开访问的 http(s) URL，不支持本地文件路径。\n"
                "本地图片请先上传到图床，或使用「图片生成」页的图生图功能（支持本地文件）。"
            )


def resource_path(relative_path: str) -> str:
    """获取资源文件的绝对路径（兼容 PyInstaller 打包环境）"""
    if hasattr(sys, "_MEIPASS"):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, relative_path)


def runtime_dir() -> str:
    """程序运行目录：源码=脚本目录；打包后=exe 所在目录（用于读写 .env）"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


class AgnesVideoGenerator:
    """Agnes 视频生成 API 工具类（异步任务模型）"""

    def __init__(self, api_key: str = None):
        """
        初始化视频生成器
        :param api_key: API 密钥，若不提供则从环境变量 AGNES_API_KEY 读取
        """
        # 运行时 .env（exe 目录）优先，内置 .env 兜底
        load_dotenv(os.path.join(runtime_dir(), ".env"))
        load_dotenv(resource_path(".env"))
        load_dotenv()

        self.api_key = api_key or os.environ.get("AGNES_API_KEY")
        if not self.api_key:
            raise ValueError("API key 未提供，请检查 .env 文件中的 AGNES_API_KEY 配置")

        self.base_url = os.environ.get("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
        self.query_url = VIDEO_QUERY_URL
        self.default_model = "agnes-video-2.5"

    def _headers(self) -> dict:
        """视频接口使用 Bearer 认证（与图片接口不同）"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def submit_video(
        self,
        prompt: str,
        images: list = None,
        model: str = None,
        seconds: str = "5",
        aspect_ratio: str = "16:9",
        seed: int = None,
    ) -> dict:
        """
        提交视频生成任务
        :param prompt: 提示词（必填）
        :param images: 参考图片 URL 列表（可选，最多 5 张；为空则纯文生视频）
        :param model: 视频模型，默认 agnes-video-2.5
        :param seconds: 视频时长字符串 "4"~"12"，默认 "5"
        :param aspect_ratio: 画幅，默认 "16:9"
        :param seed: 随机种子（可选）
        :return: 任务响应 dict（含 video_id / status 等）
        :raises Exception: 请求失败或参数错误
        """
        if not prompt or not prompt.strip():
            raise ValueError("提示词不能为空")

        if seconds not in SECONDS_OPTIONS:
            raise ValueError(f"时长必须是 {SECONDS_OPTIONS} 之一")

        if aspect_ratio not in ASPECT_RATIOS:
            raise ValueError(f"画幅必须是 {ASPECT_RATIOS} 之一")

        if images and len(images) > 5:
            raise ValueError("参考图片最多 5 张")
        validate_video_images(images)

        # 自动选择模式：有图 → reference，无图 → text
        mode = "reference" if images else "text"
        images = list(images) if images else []

        data = {
            "model": model or self.default_model,
            "prompt": prompt,
            "seconds": seconds,
            "mode": mode,
            "size": "720P",
            "aspect_ratio": aspect_ratio,
        }
        if mode == "reference":
            data["images"] = images
        if seed is not None:
            data["seed"] = seed

        try:
            response = adaptive_request(
                "POST", f"{self.base_url}/videos",
                headers=self._headers(), json=data, timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # 尽可能提取服务端错误信息
            detail = ""
            try:
                detail = response.json()
            except Exception:
                detail = response.text[:200] if response.text else ""
            # 队列满/速率限制属于可重试的临时故障，抛专用异常供上层做自动重试
            if response.status_code == 503 and "video_queue_full" in str(detail):
                raise VideoQueueFullError(
                    f"视频队列已满(HTTP 503)，请稍后重试: {detail}"
                ) from e
            if response.status_code == 429 and "rate_limit" in str(detail):
                raise VideoRateLimitError(
                    f"触发速率限制(HTTP 429)，视频任务每分钟仅允许提交 1 个: {detail}"
                ) from e
            raise Exception(f"提交视频任务失败(HTTP {response.status_code}): {detail}") from e
        except requests.exceptions.RequestException as e:
            raise Exception(f"网络请求失败: {e}") from e

    def query_video(self, video_id: str, model_name: str = None) -> dict:
        """
        查询视频任务状态
        :param video_id: 提交任务时返回的 video_id 字段
        :param model_name: 创建任务时的模型名；Flash 系模型的 reference/keyframe
                   模式必须附带（官方推荐所有模式都带），否则查询不到任务
        :return: 任务状态 dict（含 status / progress / url / error 等）
        :raises Exception: 请求失败
        """
        if not video_id:
            raise ValueError("video_id 不能为空")

        params = {"video_id": video_id}
        if model_name and model_name in FLASH_VIDEO_MODELS:
            params["model_name"] = model_name

        try:
            response = adaptive_request(
                "GET", self.query_url,
                params=params,
                headers=self._headers(),
                timeout=15,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 429:
                # 轮询被平台限速：临时故障，wait_video 会退避后继续查而不是放弃
                raise VideoRateLimitError("查询被限速(HTTP 429)") from e
            raise Exception(f"查询视频任务失败: {e}") from e
        except requests.exceptions.RequestException as e:
            raise Exception(f"查询视频任务失败: {e}") from e

    def wait_video(self, video_id: str, on_progress=None, poll_interval: float = 5.0,
                   max_polls: int = 480, model_name: str = None) -> dict:
        """
        轮询等待视频任务完成
        :param video_id: 提交任务时返回的 video_id 字段
        :param on_progress: 进度回调函数 on_progress(status, progress, result)
        :param poll_interval: 轮询间隔秒数，默认 5（过密会触发平台 429 限速）
        :param max_polls: 最大轮询次数，默认 480（约 40 分钟，含拥堵期注册延迟）
        :param model_name: 创建任务时的模型名，透传给 query_video
        :return: 最终任务状态 dict
        :raises Exception: 轮询超时或任务失败
        """
        last_progress = 0
        consecutive_errors = 0
        for _ in range(max_polls):
            try:
                result = self.query_video(video_id, model_name=model_name)
                consecutive_errors = 0
            except VideoRateLimitError:
                # 查询被限速：任务仍在服务端运行，退避后继续查而不是整个失败
                consecutive_errors += 1
                if consecutive_errors >= 6:
                    raise Exception(
                        "查询请求被持续限速(HTTP 429)，请稍等几分钟后再试；"
                        f"任务ID: {video_id} 仍在服务端保留"
                    )
                backoff = min(30, 10 * consecutive_errors)
                if on_progress:
                    on_progress("rate_limited", last_progress, {})
                time.sleep(backoff)
                continue
            except Exception as e:
                # 暂时性查询故障：拥堵期任务注册延迟实测可超过 5 分钟（期间持续
                # 返回 404），任务最终会在服务端完成；退避重试约 15 分钟才放弃
                consecutive_errors += 1
                if consecutive_errors >= 90:
                    raise Exception(
                        f"查询任务持续失败(已自动重试约 15 分钟): {e}；"
                        f"任务ID: {video_id} 仍可能已在服务端完成"
                    ) from e
                if on_progress:
                    on_progress("query_retry", last_progress, {})
                time.sleep(10)
                continue

            status = result.get("status", "unknown")
            progress = result.get("progress", 0)
            try:
                last_progress = int(progress)
            except (TypeError, ValueError):
                pass

            if on_progress:
                on_progress(status, progress, result)

            if status in DONE_STATUSES:
                if status in FAILED_STATUSES:
                    error = result.get("error") or result.get("message")
                    if error:
                        raise Exception(f"视频生成失败: {error}")
                    # 服务端没给错误详情时，把完整状态带出来便于排查
                    raise Exception(f"视频生成失败（服务端未返回错误详情）: {result}")
                return result

            time.sleep(poll_interval)

        raise Exception("视频生成超时，请稍后使用 video_id 重新查询")