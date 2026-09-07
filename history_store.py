"""生成历史记录存储模块。

每条记录包含：类型（图片/视频）、状态、创建时间、提示词、输入参数、
参考图、结果 URL、本地缓存文件与缩略图路径。

数据目录（优先级：环境变量 AGNES_HISTORY_DIR > 设置项 data_dir > 旧版默认）：
  默认    : F:\\AgnesGeneratorData（可在设置页修改）
  旧版    : %APPDATA%\\AgnesGenerator（首次启动自动迁移到新目录）
  ├─ history.json    记录索引（新 → 旧）
  ├─ media/          图片 / 视频本地缓存
  └─ thumbs/         列表缩略图

说明：PyInstaller 打包后的 exe 常装在只读目录，数据放独立目录可避免
写入被拒；「源码运行」与「exe 运行」共用同一份历史。

所有写操作带线程锁，索引文件采用「临时文件 + 原子替换」，
避免写入中断导致历史全部丢失。
"""
import json
import os
import shutil
import threading
import uuid
from datetime import datetime
from io import BytesIO

from PIL import Image

_LOCK = threading.RLock()

_HISTORY_FILE = "history.json"
_MEDIA_DIR = "media"
_THUMB_DIR = "thumbs"
_TMP_SUFFIX = ".tmp"

# 超出后自动清理最旧的记录（同时删除其缓存文件）
MAX_RECORDS = 500
# 列表缩略图尺寸
THUMB_SIZE = (160, 160)

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv"}


# ===================== 目录与文件 =====================

def get_data_dir() -> str:
    """历史数据根目录：环境变量 > 设置项 data_dir > 旧版默认（%APPDATA%）"""
    env = (os.environ.get("AGNES_HISTORY_DIR") or "").strip()
    if env:
        return os.path.abspath(env)
    try:
        import app_config
        configured = (app_config.get("data_dir") or "").strip()
        if configured:
            return os.path.abspath(configured)
    except Exception:
        pass
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "AgnesGenerator")
    return os.path.join(os.path.expanduser("~"), ".agnes_generator")


def _legacy_data_dir() -> str:
    """旧版默认数据目录（迁移源）"""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "AgnesGenerator")
    return os.path.join(os.path.expanduser("~"), ".agnes_generator")


def migrate_legacy() -> bool:
    """把旧版 %APPDATA% 下的历史数据一次性迁移到当前数据目录。

    幂等：新目录已有 history.json 时不做任何事；返回是否发生了迁移。
    """
    new = os.path.abspath(get_data_dir())
    old = os.path.abspath(_legacy_data_dir())
    if os.path.normcase(new) == os.path.normcase(old):
        return False
    old_index = os.path.join(old, _HISTORY_FILE)
    new_index = os.path.join(new, _HISTORY_FILE)
    if not os.path.isfile(old_index) or os.path.exists(new_index):
        return False
    ensure_dirs()
    shutil.move(old_index, new_index)
    for sub in (_MEDIA_DIR, _THUMB_DIR):
        src_dir = os.path.join(old, sub)
        dst_dir = os.path.join(new, sub)
        if not os.path.isdir(src_dir):
            continue
        os.makedirs(dst_dir, exist_ok=True)
        for name in os.listdir(src_dir):
            src = os.path.join(src_dir, name)
            dst = os.path.join(dst_dir, name)
            if not os.path.exists(dst):
                shutil.move(src, dst)
    return True


def get_media_dir() -> str:
    return os.path.join(get_data_dir(), _MEDIA_DIR)


def get_thumb_dir() -> str:
    return os.path.join(get_data_dir(), _THUMB_DIR)


def get_history_file() -> str:
    return os.path.join(get_data_dir(), _HISTORY_FILE)


def ensure_dirs() -> str:
    """确保数据目录存在，返回根目录"""
    root = get_data_dir()
    for d in (root, get_media_dir(), get_thumb_dir()):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
    return root


def _new_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


# ===================== 读写 =====================

def load_history() -> list:
    """读取全部记录（最新的在前）；文件缺失或损坏时返回空列表"""
    path = get_history_file()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [r for r in data if isinstance(r, dict) and r.get("id")]


def _save_all(records: list):
    ensure_dirs()
    path = get_history_file()
    tmp = path + _TMP_SUFFIX
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _safe_remove(path: str):
    """仅删除数据目录内的文件，避免误删用户文件"""
    if not path:
        return
    try:
        root = os.path.normcase(os.path.abspath(get_data_dir()))
        target = os.path.normcase(os.path.abspath(path))
        if not target.startswith(root + os.sep):
            return
        if os.path.exists(target):
            os.remove(target)
    except Exception:
        pass


def _delete_assets(rec: dict):
    _safe_remove(rec.get("media_path"))
    _safe_remove(rec.get("thumb_path"))


def _prune(records: list):
    """就地裁剪：超出 MAX_RECORDS 的最旧记录连同文件一起删除"""
    while len(records) > MAX_RECORDS:
        _delete_assets(records.pop())


# ===================== 记录操作 =====================

def add_record(kind: str, prompt: str, params: dict = None, refs: list = None,
               result_url: str = None, status: str = "success",
               meta: dict = None, error: str = None) -> dict:
    """新增一条历史记录并返回它

    :param kind: "image" / "video"
    :param status: "success" / "failed"
    """
    ensure_dirs()
    now = datetime.now()
    rec = {
        "id": _new_id(),
        "type": kind,
        "status": status,
        "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": now.timestamp(),
        "prompt": prompt or "",
        "params": params or {},
        "refs": [str(r) for r in (refs or []) if r],
        "result_url": result_url,
        "media_path": None,
        "thumb_path": None,
        "meta": meta or {},
        "error": error,
    }
    with _LOCK:
        records = load_history()
        records.insert(0, rec)
        _prune(records)
        _save_all(records)
    return rec


def update_record(record_id: str, **fields) -> dict:
    """更新记录字段（如补写本地缓存路径），返回更新后的记录"""
    if not record_id:
        return None
    with _LOCK:
        records = load_history()
        for r in records:
            if r.get("id") == record_id:
                r.update(fields)
                _save_all(records)
                return dict(r)
    return None


def get_record(record_id: str) -> dict:
    for r in load_history():
        if r.get("id") == record_id:
            return r
    return None


def delete_record(record_id: str) -> bool:
    """删除记录及其缓存文件"""
    with _LOCK:
        records = load_history()
        rest = [r for r in records if r.get("id") != record_id]
        if len(rest) == len(records):
            return False
        for r in records:
            if r.get("id") == record_id:
                _delete_assets(r)
        _save_all(rest)
        return True


def clear_history() -> int:
    """清空全部记录，返回被删除的条数"""
    with _LOCK:
        records = load_history()
        for r in records:
            _delete_assets(r)
        _save_all([])
        # 清理可能残留的孤儿文件
        for folder in (get_media_dir(), get_thumb_dir()):
            try:
                for name in os.listdir(folder):
                    _safe_remove(os.path.join(folder, name))
            except Exception:
                pass
        return len(records)


# ===================== 素材缓存 =====================

def save_image_asset(img_data: bytes, record_id: str) -> tuple:
    """把图片字节写入本地缓存，并生成列表缩略图

    :return: (media_path, thumb_path)
    """
    ensure_dirs()
    img = Image.open(BytesIO(img_data))
    fmt = (img.format or "PNG").upper()
    ext = {
        "JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp",
        "BMP": ".bmp", "GIF": ".gif",
    }.get(fmt, ".png")

    media_path = os.path.join(get_media_dir(), record_id + ext)
    with open(media_path, "wb") as f:
        f.write(img_data)

    thumb = img.copy()
    thumb.thumbnail(THUMB_SIZE, Image.LANCZOS)
    if thumb.mode in ("RGBA", "LA", "P"):
        thumb = thumb.convert("RGBA")
        bg = Image.new("RGB", thumb.size, (255, 255, 255))
        bg.paste(thumb, mask=thumb.split()[-1])
        thumb = bg
    else:
        thumb = thumb.convert("RGB")
    thumb_path = os.path.join(get_thumb_dir(), record_id + ".png")
    thumb.save(thumb_path, "PNG")
    return media_path, thumb_path


def save_media_bytes(data: bytes, record_id: str, ext: str = ".mp4") -> str:
    """保存视频等二进制结果，返回文件路径"""
    ensure_dirs()
    if not ext.startswith("."):
        ext = "." + ext
    path = os.path.join(get_media_dir(), record_id + ext)
    with open(path, "wb") as f:
        f.write(data)
    return path


def guess_ext(url: str, kind: str = "image") -> str:
    """从 URL 猜测文件扩展名"""
    try:
        name = url.split("?")[0].rsplit("/", 1)[-1]
        ext = os.path.splitext(name)[1].lower()
    except Exception:
        ext = ""
    if ext in _IMAGE_EXTS or ext in _VIDEO_EXTS:
        return ext
    return ".mp4" if kind == "video" else ".png"
