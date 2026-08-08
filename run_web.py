"""ZQuant Flet Web 启动脚本（开发/本地模式）。

直接运行：python run_web.py
或供 `flet run -w run_web.py` 使用。

关键：显式指定 view=FLET_APP_WEB —— 纯 Web 服务器，不弹桌面窗口。
默认 FLET_APP（桌面窗口）在受限/无头环境会卡死宿主窗口。
"""

import sys
from pathlib import Path

# 确保能 import zquant(基于脚本位置解析 src,不依赖 cwd)
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT / "src"))

import flet as ft

from zquant.ui.debug_log import get_logger
from zquant.ui.main import main

_log = get_logger("zquant.ui.run")


def _patch_flet_web_template() -> bool:
    """修补 Flet 0.86.5 的 web 模板 bug(multiView=false 无 addView)。

    若模板已带 [zquant-fix] 标记则跳过；否则就地修补。
    返回 True 表示已修补/已存在。
    """
    import site

    try:
        for base in site.getsitepackages():
            tpl = Path(base) / "flet_web" / "web" / "index.html"
            if not tpl.exists():
                continue
            html = tpl.read_text(encoding="utf-8")
            if "[zquant-fix]" in html:
                _log.info("模板已带 zquant-fix 补丁，跳过: %s", tpl)
                return True
            # 1) multiView=false 分支加 addView
            old = (
                "      }\n    });\n  </script>\n\n  <!-- fletAppConfig -->"
            )
            add = (
                "      } else if (document.querySelector('#view-1')) {\n"
                "        console.log(flutterApp.addView({\n"
                "          hostElement: document.querySelector('#view-1'),\n"
                "          viewConstraints: { maxHeight: Infinity, minHeight: 0, minWidth: 0, maxWidth: Infinity }\n"
                "        }));\n"
                "        console.log('[zquant-fix] single view addView done');\n"
                "      }\n"
                "    });\n  </script>\n\n  <!-- fletAppConfig -->"
            )
            if old in html:
                html = html.replace(old, add)
            # 2) 启用 #view-1 宿主元素
            old_view = (
                "  <!-- <h1>View 1</h1>\n"
                "  <div id=\"view-1\" style=\"display: flex; justify-content: center;\"></div>\n"
                "  <h1>View 2</h1>\n"
                "  <div id=\"view-2\"></div> -->"
            )
            new_view = (
                "  <!-- [zquant-fix] 启用 #view-1 作为单 view 渲染宿主 -->\n"
                "  <div id=\"view-1\" style=\"display: flex; justify-content: center; width: 100%; height: 100%;\"></div>\n"
                "  <div id=\"view-2\" style=\"display: none;\"></div>"
            )
            if old_view in html:
                html = html.replace(old_view, new_view)
            tpl.write_text(html, encoding="utf-8")
            _log.info("已修补 flet web 模板: %s", tpl)
            return True
    except Exception as e:  # noqa: BLE001
        _log.error("模板修补失败: %s", e)
    return False


if __name__ == "__main__":
    _log.info("ZQuant Web 启动 (flet %s)", ft.__version__)
    _patch_flet_web_template()
    ft.run(
        main,
        view=ft.AppView.FLET_APP_WEB,          # 纯 Web 服务器(不弹桌面窗口)
        web_renderer=ft.WebRenderer.CANVAS_KIT,  # CanvasKit 渲染
        port=8555,
        host="127.0.0.1",
    )
