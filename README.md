# Windsurf Register

A Flask-based web app for batch registration workflows, task tracking, and export management.

## Features

- Start and stop batch tasks from a web UI
- Run registration workers with configurable concurrency
- Track runtime status and incremental logs
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
  config.example.json       # Config template (copy to config.json)
  task_exports/             # Task export files (created at runtime)
  backups/                  # Backup files (created at runtime)
```

## Requirements

- Python 3.8+
- pip

## Quick Start

1. Create and activate a virtual environment

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .\.venv\Scripts\Activate.ps1
```

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Initialize config

```bash
cp config.example.json config.json
```

Windows PowerShell alternative:

```powershell
Copy-Item .\config.example.json .\config.json
```

4. Run the server

```bash
python server.py
```

Default URLs:

- `http://127.0.0.1:5000`
- `http://0.0.0.0:5000`

## Nginx Reverse Proxy Example

Use this when exposing the app under `/windsurf-register/`:

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

## Main Endpoints

- `GET /` - index page
- `GET /status` - runtime status and incremental logs
- `POST /start_batch` - start batch task
- `POST /stop` - stop running task
- `GET /accounts` - results of current/latest task
- `GET /exports` - recent exports
- `GET /download?format=raw|custom|session` - download latest export
- `POST /config` and `GET /config` - update/read proxy config

## Data Safety Notes

- `config.json` can contain local proxy details and is ignored by Git
- `accounts*.json` and `cockpit_direct_import*.json` may contain sensitive data and are ignored by Git
- Do not commit real credentials, tokens, or private proxy information
