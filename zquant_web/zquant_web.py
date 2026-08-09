"""ZQuant Reflex 应用入口（M7 方案 v2: Reflex 全栈接管）。

Reflex 直接 import zquant core（不走 API 层）。
入口脚本启动时把 src/ 加入 sys.path，确保能 import zquant.*。
"""

import sys
from pathlib import Path

import reflex as rx

from rxconfig import config

# 确保能 import zquant（项目 src/ 目录）
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

# 验证 core 可导入（骨架验证用）
from zquant.signals import SIGNAL_NAMES  # noqa: E402


class State(rx.State):
    """The app state."""

    signal_names: list[str] = list(SIGNAL_NAMES)


def index() -> rx.Component:
    # Welcome Page (Index)
    return rx.container(
        rx.color_mode.button(position="top-right"),
        rx.vstack(
            rx.heading("ZQuant · Reflex 骨架", size="9"),
            rx.text("core 导入验证:", size="5"),
            rx.foreach(State.signal_names, lambda name: rx.text(name, size="3")),
            rx.link(
                rx.button("Check out our docs!"),
                href="https://reflex.dev/docs/getting-started/introduction/",
                is_external=True,
            ),
            spacing="5",
            justify="center",
            min_height="85vh",
        ),
    )


app = rx.App()
app.add_page(index)
