# Windsurf Register

基于 Flask 的批量注册与结果导出工具，前端页面与后端服务集成在同一个项目中。

## 功能说明

- Web 页面控制批量任务启动/停止
- 支持并发线程执行注册任务
- 支持任务状态与日志查询
- 支持导出任务结果（raw/custom/session）
- 支持代理配置在线更新并持久化到 `config.json`

## 目录结构

```text
WindsurfRegister_Deploy/
  server.py                 # Flask 后端入口（默认 5000 端口）
  templates/index.html      # 前端页面
  requirements.txt          # Python 依赖
  start.sh                  # Linux 启动脚本
  start.bat                 # Windows 启动脚本
  config.example.json       # 配置示例（请复制为 config.json）
  task_exports/             # 任务导出文件（运行后生成）
  backups/                  # 备份目录（运行后生成）
```

## 环境要求

- Python 3.8+
- pip

## 快速开始

1. 创建并激活虚拟环境

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .\.venv\Scripts\Activate.ps1
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 初始化配置

```bash
cp config.example.json config.json
```

Windows 可手动复制：

```powershell
Copy-Item .\config.example.json .\config.json
```

4. 启动服务

```bash
python server.py
```

默认监听：

- `http://127.0.0.1:5000`
- `http://0.0.0.0:5000`

## 反向代理（Nginx 示例）

如果你要通过 `/windsurf-register/` 访问，可参考：

```nginx
location = /windsurf-register {
    return 301 /windsurf-register/;
}

location ^~ /windsurf-register/ {
    proxy_pass http://127.0.0.1:5000/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
}
```

## 常用接口

- `GET /`：首页
- `GET /status`：运行状态与增量日志
- `POST /start_batch`：启动批量任务
- `POST /stop`：停止任务
- `GET /accounts`：当前任务账号结果
- `GET /exports`：最近导出任务
- `GET /download?format=raw|custom|session`：下载最新任务导出
- `POST /config` / `GET /config`：读写代理配置

## 数据与安全建议

- `config.json` 可能包含本地代理信息，默认不入库
- `accounts*.json`、`cockpit_direct_import*.json` 可能包含敏感账号数据，默认不入库
- 请不要将真实账号、令牌、代理凭据提交到 GitHub

