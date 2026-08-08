"""API 服务启动入口：zquant-api 或 python -m zquant.api。"""

import uvicorn


def main() -> None:
    """启动 ZQuant API 服务（默认 127.0.0.1:8000）。"""
    uvicorn.run("zquant.api.app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
