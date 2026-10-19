# 参与开发

## 环境

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt -r requirements-build.txt
python run.py
```

## 代码风格

- Python 3.11+，不用 `from __future__` 之外的兼容层；
- 类型标注尽量写，公共函数写 docstring；
- 界面代码只管布局和交互，业务逻辑放 `qqbot_core` 或 `services/`；
- 不要新增不必要的依赖：内核只依赖 `websockets`，界面只依赖 `PySide6`。

## 测试

```powershell
python tests\test_core.py     # 41 项
python tests\e2e_test.py      # 假 NapCat，正/反向
python tests\test_chat.py     # 试聊会话
```

改了界面，可以离屏导出截图对比：

```powershell
python -m qqbot_generator --screenshot build\shots
```

## 加一个页面

1. 在 `src/qqbot_generator/pages/` 新建 `my_page.py`：

```python
from .base import BasePage

class MyPage(BasePage):
    key = "my"
    title = "我的页面"
    subtitle = "一句话说明"

    def build(self) -> None:
        ...
```

2. 在 `pages/__init__.py` 的 `PAGES` 列表里加一行；
3. 在 `widgets/sidebar.py` 的 `NAV_GROUPS` 里加导航项。

## 提 PR

- 描述改了什么、为什么；
- 附上测试结果；
- 界面改动附截图（`docs/screenshots/` 用同样的尺寸）。
