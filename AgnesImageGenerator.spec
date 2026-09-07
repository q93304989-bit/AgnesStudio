# -*- mode: python ; coding: utf-8 -*-

import os
import customtkinter

_ctk_assets = os.path.join(os.path.dirname(customtkinter.__file__), "assets")

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('.env', '.'),
        ('app_icon.png', '.'),
        ('app_icon.ico', '.'),
        (_ctk_assets, os.path.join('customtkinter', 'assets')),
    ],
    hiddenimports=[
        'PIL._tkinter_finder',
        'customtkinter',
        'ui_theme',     # 集中式设计 token（浅 / 深双主题，main/gallery/history 共用）
        'history_store',
        'history_ui',
        'gallery_ui',   # 视觉陈列版：瀑布流 / Lightbox / 图示画幅选择
        'video_core',
        'http_session',
        'image_host',
        'app_config',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 用 conda base 环境打包时会把整个科学计算栈拖进来（MKL 约 600MB +
    # IPython/Sphinx/Jupyter/pytest 等），本项目只用到 PIL / customtkinter /
    # requests，故显式排除。剔除后 exe 由 320MB 降至约 30MB。
    excludes=[
        'numpy', 'matplotlib', 'scipy', 'pandas', 'sklearn', 'skimage',
        'IPython', 'ipykernel', 'jupyter_client', 'jupyter_core',
        'nbformat', 'nbconvert', 'notebook', 'qtconsole',
        'sphinx', 'docutils', 'pygments', 'jedi', 'parso',
        'prompt_toolkit', 'pytest', '_pytest', 'pluggy', 'iniconfig',
        'twisted', 'paramiko', 'yapf', 'snowballstemmer', 'alabaster',
        'babel', 'imagesize', 'roman', 'tornado', 'zmq', 'traitlets',
        'PIL.ImageQt',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Agnes图像生成小工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
)
