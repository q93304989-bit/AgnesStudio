"""应用设置模块：settings.json 的读写与默认值管理。

存储位置（固定，不随数据目录变动）：
  Windows : %APPDATA%\\AgnesGenerator\\settings.json
数据目录（历史/媒体缓存，可在设置里改，默认 F 盘）：
  默认    : F:\\AgnesGeneratorData
  覆盖顺序: 环境变量 AGNES_HISTORY_DIR > settings.data_dir

说明：密钥仍以程序目录 .env 为准（12-Factor 惯例），settings 只管偏好；
两者分离，换机器时拷 .env + settings.json 即可完整还原。
"""
import json
import os
import threading

_LOCK = threading.RLock()

_CONFIG_DIR = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"), "AgnesGenerator")
_CONFIG_FILE = os.path.join(_CONFIG_DIR, "settings.json")
_TMP_SUFFIX = ".tmp"

DEFAULT_DATA_DIR = r"F:\AgnesGeneratorData"

DEFAULTS = {
    "theme": "system",          # system / light / dark
    "theme_auto_restart": False,  # 切换主题后自动重启程序（彻底应用，避免残留）
    "network_mode": "auto",     # auto / direct / proxy
    "data_dir": DEFAULT_DATA_DIR,
    "img_model": "",            # 空 = 使用界面选项第一项
    "img_size": "",
    "vid_model": "",
    "vid_seconds": "",
    "vid_aspect": "",
    "gh_token": "",             # GitHub 图床 Personal Access Token
    "gh_repo": "",              # GitHub 图床仓库（如 user/my-images）
}

_cache = None


def _config_file() -> str:
    env = (os.environ.get("AGNES_SETTINGS_FILE") or "").strip()
    return env if env else _CONFIG_FILE


def load() -> dict:
    """读取设置（默认值兜底；文件缺失/损坏返回默认值）"""
    global _cache
    with _LOCK:
        if _cache is not None:
            return dict(_cache)
        merged = dict(DEFAULTS)
        try:
            with open(_config_file(), "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    if k in merged:
                        merged[k] = v
        except Exception:
            pass
        _cache = merged
        return dict(_cache)


def save(new_settings: dict):
    """整体保存（覆盖式）；临时文件 + 原子替换"""
    global _cache
    with _LOCK:
        merged = dict(DEFAULTS)
        merged.update({k: v for k, v in (new_settings or {}).items()
                       if k in merged})
        path = _config_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + _TMP_SUFFIX
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        _cache = merged


def update(**fields):
    """局部更新若干设置项并保存"""
    merged = load()
    merged.update(fields)
    save(merged)


def get(key: str, fallback=None):
    """读取单个设置项"""
    v = load().get(key, DEFAULTS.get(key))
    return v if v not in (None, "") else fallback


def reset_cache():
    """清空内存缓存（外部改了 settings.json 后强制重读）"""
    global _cache
    with _LOCK:
        _cache = None
