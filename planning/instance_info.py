"""Repository identity captured once when an instance starts."""
import os
from pathlib import Path
import subprocess


def instance_info(root):
    root = Path(root).resolve()
    info = dict(folder=root.name, branch=None, commit=None, dirty=False)
    def git(*args):
        return subprocess.run(['git','-C',str(root),*args], check=True, capture_output=True,
            encoding='utf-8', timeout=10, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0).stdout.strip()
    try:
        info.update(branch=git('branch','--show-current') or None, commit=git('rev-parse','HEAD'),
                    dirty=bool(git('status','--porcelain')))
    except (OSError, subprocess.SubprocessError):
        pass
    return info


def label(info):
    if not isinstance(info,dict):
        return '未知文件夹 未知提交'
    return f"{info.get('folder','未知文件夹')} · {info.get('branch') or '无分支'} · {(info.get('commit') or '无提交')[:8]}"
