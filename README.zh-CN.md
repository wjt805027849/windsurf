# Windsurf Register（中文说明）

基于 Flask 的批量注册工作流工具，提供 Web 控制台、任务状态追踪和结果导出能力。

[English](README.md) | 简体中文

## 功能

- 在 Web 页面中启动和停止批量任务
- 按可配置并发线程执行注册流程
- 查看运行状态与增量日志
- 按多种格式下载导出结果（`raw`、`custom`、`session`）
- 在线更新代理配置并持久化到 `config.json`

## 项目结构

```text
WindsurfRegister_Deploy/
  server.py                 # Flask 应用入口（5000 端口）
  templates/index.html      # Web 页面
  requirements.txt          # Python 依赖
  start.sh                  # Linux 启动脚本
  start.bat                 # Windows 启动脚本
  config.example.json       # 配置模板（复制为 config.json）
  task_exports/             # 任务导出目录（运行后生成）
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

Windows PowerShell 可用：

```powershell
Copy-Item .\config.example.json .\config.json
```

4. 启动服务

```bash
python server.py
```

默认访问地址：

- `http://127.0.0.1:5000`
- `http://0.0.0.0:5000`

## Nginx 反向代理示例

若你希望通过 `/windsurf-register/` 暴露服务，可使用：

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

## 主要接口

- `GET /`：首页
- `GET /status`：运行状态与增量日志
- `POST /start_batch`：启动任务
- `POST /stop`：停止任务
- `GET /accounts`：当前/最近任务结果
- `GET /exports`：最近导出任务列表
- `GET /download?format=raw|custom|session`：下载最近任务导出
- `POST /config` 与 `GET /config`：更新/读取代理配置

## 数据安全建议

- `config.json` 可能包含本地代理信息，默认已被 Git 忽略
- `accounts*.json`、`cockpit_direct_import*.json` 可能包含敏感数据，默认已被 Git 忽略
- 不要提交真实账号、令牌、私有代理凭据

