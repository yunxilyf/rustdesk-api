"""视图汇总：仅做 re-export，路由在 api/urls.py 中显式引用各视图。"""

from .views_front import *  # noqa: F401,F403
from .views_api import *  # noqa: F401,F403
