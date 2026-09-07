"""
Agnes 图像生成核心模块
集成：文生图、图生图(URL)、图生图(本地图片/base64)
"""
import os
import sys
import base64
import requests
from dotenv import load_dotenv

from http_session import adaptive_request


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


class AgnesImageGenerator:
    """Agnes 图像生成 API 工具类"""

    def __init__(self, api_key: str = None):
        """
        初始化生成器
        :param api_key: API 密钥，若不提供则从环境变量 AGNES_API_KEY 读取
        """
        # 优先从当前程序目录加载 .env，兼容打包后的 exe 同级目录；
        # 运行时 .env（exe 目录）覆盖内置 .env（PyInstaller 打包内）
        load_dotenv(os.path.join(runtime_dir(), ".env"))
        load_dotenv(resource_path(".env"))
        load_dotenv()

        self.api_key = api_key or os.environ.get("AGNES_API_KEY")
        if not self.api_key:
            raise ValueError("API key 未提供，请检查 .env 文件中的 AGNES_API_KEY 配置")

        base = os.environ.get("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1").strip().rstrip("/")
        self.base_url = base + "/images/generations"
        self.default_model = "agnes-image-2.1-flash"
        self.default_size = "1024x768"

    def _post_request(self, data: dict) -> str:
        """
        发送请求并提取图片 URL
        :param data: 请求体
        :return: 生成的图片 URL
        :raises Exception: 请求失败或响应异常时抛出
        """
        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json"
        }

        try:
            response = adaptive_request("POST", self.base_url, headers=headers, json=data, timeout=120)
            response.raise_for_status()  # 如果状态码不是 2xx，抛出 HTTPError
            result = response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"网络请求失败: {e}") from e
        except ValueError as e:
            raise Exception(f"响应解析失败: {e}") from e

        # 检查响应结构并提取图片 URL
        if "data" in result and len(result["data"]) > 0 and "url" in result["data"][0]:
            return result["data"][0]["url"]
        else:
            error_msg = result.get("error", "未知错误")
            raise Exception(f"生成图片失败: {error_msg}")

    def generate_text_to_image(
        self,
        prompt: str,
        model: str = None,
        size: str = None,
        extra_body: dict = None
    ) -> str:
        """
        文生图：根据文字描述生成图片
        :param prompt: 提示词（必填）
        :param model: 模型名称，默认 agnes-image-2.1-flash
        :param size: 图片尺寸，默认 1024x768
        :param extra_body: 额外请求体参数
        :return: 生成的图片 URL
        """
        if not prompt or not prompt.strip():
            raise ValueError("提示词不能为空")

        data = {
            "model": model or self.default_model,
            "prompt": prompt,
            "size": size or self.default_size,
            "extra_body": extra_body if extra_body is not None else {"response_format": "url"}
        }
        return self._post_request(data)

    def generate_image_to_image_url(
        self,
        prompt: str,
        image_url: str,
        model: str = None,
        size: str = None,
        extra_body: dict = None
    ) -> str:
        """
        图生图（图片 URL）：基于参考图片 URL 生成新图片
        :param prompt: 提示词（必填）
        :param image_url: 参考图片的 URL（必填）
        :param model: 模型名称
        :param size: 图片尺寸
        :param extra_body: 额外请求体参数
        :return: 生成的图片 URL
        """
        if not prompt or not prompt.strip():
            raise ValueError("提示词不能为空")
        if not image_url or not image_url.strip():
            raise ValueError("图片 URL 不能为空")

        data = {
            "model": model or self.default_model,
            "prompt": prompt,
            "size": size or self.default_size,
            "extra_body": extra_body if extra_body is not None else {
                "image": [image_url],
                "response_format": "url"
            }
        }
        return self._post_request(data)

    def generate_image_to_image_local(
        self,
        prompt: str,
        image_path: str,
        model: str = None,
        size: str = None,
        extra_body: dict = None
    ) -> str:
        """
        图生图（本地图片）：读取本地图片并 base64 编码后生成新图片
        :param prompt: 提示词（必填）
        :param image_path: 本地图片文件路径（必填）
        :param model: 模型名称
        :param size: 图片尺寸
        :param extra_body: 额外请求体参数
        :return: 生成的图片 URL
        """
        if not prompt or not prompt.strip():
            raise ValueError("提示词不能为空")
        if not image_path or not os.path.exists(image_path):
            raise ValueError(f"本地图片不存在: {image_path}")

        # 读取本地文件并转 base64
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

        data = {
            "model": model or self.default_model,
            "prompt": prompt,
            "size": size or self.default_size,
            "extra_body": extra_body if extra_body is not None else {
                "image": [image_b64],
                "response_format": "url"
            }
        }
        return self._post_request(data)

    @staticmethod
    def _guess_mime(path: str) -> str:
        """根据文件扩展名猜测 MIME 类型"""
        ext = os.path.splitext(path)[1].lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".bmp": "image/bmp",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return mime_map.get(ext, "image/png")

    def generate_images(
        self,
        prompt: str,
        images: list = None,
        model: str = None,
        size: str = None,
        extra_body: dict = None
    ) -> str:
        """
        统一图片生成入口：无参考图 → 文生图；有参考图 → 图生图（支持多图）
        每张参考图可以是公网 URL，也可以是本地文件路径（自动转 base64 data URI）
        :param prompt: 提示词（必填）
        :param images: 参考图列表（URL 或本地路径，可选）
        :param model: 模型名称
        :param size: 图片尺寸
        :param extra_body: 额外请求体参数（覆盖自动构造时使用）
        :return: 生成的图片 URL
        """
        if not prompt or not prompt.strip():
            raise ValueError("提示词不能为空")

        data = {
            "model": model or self.default_model,
            "prompt": prompt,
            "size": size or self.default_size,
        }

        # 处理参考图：本地路径转 data URI，其余视为 URL
        refs = []
        if images:
            for img in images:
                if not img or not str(img).strip():
                    continue
                img = str(img).strip()
                if os.path.exists(img):
                    with open(img, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    refs.append(f"data:{self._guess_mime(img)};base64,{b64}")
                else:
                    refs.append(img)

        if refs:
            data["extra_body"] = extra_body if extra_body is not None else {
                "image": refs,
                "response_format": "url",
            }
        else:
            data["extra_body"] = extra_body if extra_body is not None else {
                "response_format": "url",
            }

        return self._post_request(data)


# ---------- 使用示例 ----------
if __name__ == "__main__":
    generator = AgnesImageGenerator()
    print("Agnes 图像生成核心模块测试")

    # 文生图
    try:
        url = generator.generate_text_to_image("日出时分薄雾峡谷上方的发光浮空城市")
        print("文生图 URL:", url)
    except Exception as e:
        print("文生图错误:", e)