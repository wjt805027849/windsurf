# Windsurf 注册工具打包脚本

这个脚本将帮助您将项目整理为适合部署到服务器的结构。

## 目录结构
打包后的文件夹 `WindsurfRegister_Deploy` 将包含：
- `server.py`: 后端 Flask 服务
- `templates/index.html`: 前端界面
- `requirements.txt`: 依赖库清单
- `start.bat`: Windows 启动脚本
- `start.sh`: Linux 启动脚本
- `README.md`: 部署说明

## 部署步骤
1.  **环境准备**：服务器需安装 Python 3.8+。
2.  **安装依赖**：运行 `pip install -r requirements.txt`。
3.  **配置代理**：根据服务器环境，在界面或 `server.py` 中修改默认代理地址。
4.  **运行服务**：
    - Windows: 双击 `start.bat`
    - Linux: `bash start.sh`
