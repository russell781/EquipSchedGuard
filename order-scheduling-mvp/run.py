"""线上部署启动入口：读取 PORT 环境变量并绑定 0.0.0.0。

本地开发仍可用 uvicorn app.main:app --reload --port 8000；
线上部署由沙箱注入 PORT，本脚本保证正确监听。
"""
import os

import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
