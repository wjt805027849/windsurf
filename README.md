# Windsurf Register

A Flask-based web app for batch registration workflows, task tracking, proxy rotation, and export management.

English | [简体中文](README.zh-CN.md)

## Screenshots

Desktop overview:

![Dashboard Overview](assets/screenshots/dashboard-overview.png)

Desktop full view:

![Dashboard Tall](assets/screenshots/dashboard-tall.png)

Mobile view:

![Dashboard Mobile](assets/screenshots/dashboard-mobile.png)

## Features

- Start and stop batch tasks from a web UI
- Run registration workers with configurable concurrency
- Rotate across a proxy pool
- Track provider health, timings, and fallback behavior
- Download export data in multiple formats (`raw`, `custom`, `session`)
- Update and persist proxy settings via `config.json`

## Project Structure

```text
WindsurfRegister_Deploy/
  server.py                 # Flask app entrypoint (port 5000)
  templates/index.html      # Web UI
  requirements.txt          # Python dependencies
  start.sh                  # Linux start script
  start.bat                 # Windows start script
  config.example.json       # Config template
  assets/screenshots/       # README screenshots
  task_exports/             # Task export files
  backups/                  # Backup files
```

## Quick Start

1. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Initialize config

```bash
cp config.example.json config.json
```

Windows PowerShell:

```powershell
Copy-Item .\config.example.json .\config.json
```

4. Run the server

```bash
python server.py
```

Default URL:

- `http://127.0.0.1:5000`

## Main Endpoints

- `GET /` - index page
- `GET /status` - runtime status and incremental logs
- `GET /providers` - temp-mail source health and metrics
- `POST /start_batch` - start batch task
- `POST /stop` - stop running task
- `GET /accounts` - results of current/latest task
- `GET /exports` - recent exports
- `GET /download?format=raw|custom|session` - download latest export
- `POST /config` and `GET /config` - update/read proxy config

## Data Safety Notes

- `config.json` can contain local proxy details and is ignored by Git
- `accounts*.json` and `cockpit_direct_import*.json` can contain sensitive data and are ignored by Git
- Do not commit real credentials, tokens, or private proxy information

## Links

[Linux.do](https://linux.do/)
