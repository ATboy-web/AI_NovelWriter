import sys
from pathlib import Path

# 将项目根目录加入 Python 路径
_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
