"""模型汇总入口：Django 只注册 api 一个 app，模型按用途分在三个模块里。"""

from .models_work import *
from .models_user import *
from .models_pro import *
