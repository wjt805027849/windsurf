import io
import json
import os
import random
import re
import string
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template, request, send_file
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = Flask(__name__)

BASE = "https://windsurf.com"
EXPORT_DIR = Path("task_exports")
ALL_ACCOUNTS_FILE = Path("accounts_all.json")
BACKUP_DIR = Path("backups")
JOURNAL_DIR = BACKUP_DIR / "journals"
SNAPSHOT_DIR = BACKUP_DIR / "snapshots"
CONFIG_FILE = Path("config.json")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]


def ensure_export_dir():
    EXPORT_DIR.mkdir(exist_ok=True)


def ensure_backup_dirs():
    BACKUP_DIR.mkdir(exist_ok=True)
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_json_file(path: Path, default):
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def write_json_file(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def append_jsonl(path: Path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def sanitize_for_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", value)


def snapshot_json_file(path: Path, label: str):
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_name = f"{path.stem}_{sanitize_for_filename(label)}_{stamp}{path.suffix}"
    write_json_file(SNAPSHOT_DIR / snapshot_name, read_json_file(path, []))


def get_result_identity(item):
    return (
        item.get("email")
        or item.get("github_email")
        or item.get("original_email")
        or item.get("sessionToken")
        or item.get("github_access_token")
        or ""
    )


def get_export_file_path(filename: str) -> Path:
    task_path = EXPORT_DIR / filename
    if task_path.exists():
        return task_path
    return Path(filename)


def get_session(proxies):
    session = requests.Session()
    if proxies:
        session.proxies.update({k: v for k, v in proxies.items() if v})
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def should_fallback_direct(exc):
    msg = str(exc)
    return (
        "Failed to establish a new connection" in msg
        and ("127.0.0.1" in msg or "localhost" in msg)
        and ("7897" in msg or "7890" in msg or "proxy" in msg.lower())
    )


class GlobalState:
    def __init__(self):
        self.proxies = {
            "http": "http://127.0.0.1:7890",
            "https": "http://127.0.0.1:7890",
        }
        self.logs = []
        self.is_running = False
        self.should_stop = False
        self.stop_on_success = False
        self.last_log_index = 0
        self.active_threads = 0
        self.total_to_register = 0
        self.completed_count = 0
        self.failed_count = 0
        self.start_time = None
        self.success_per_hour = 0.0
        self.export_custom_format = False
        self.current_task = None
        self.file_lock = threading.Lock()


state = GlobalState()


def load_runtime_config():
    data = read_json_file(CONFIG_FILE, {})
    if not isinstance(data, dict):
        return
    http_proxy = str(data.get("http", "")).strip()
    https_proxy = str(data.get("https", "")).strip()
    if http_proxy:
        state.proxies["http"] = http_proxy
    if https_proxy:
        state.proxies["https"] = https_proxy


def save_runtime_config():
    write_json_file(
        CONFIG_FILE,
        {
            "http": state.proxies.get("http", ""),
            "https": state.proxies.get("https", ""),
            "updated_at": now_str(),
        },
    )


def add_log(msg):
    timestamp = time.strftime("%H:%M:%S")
    full_msg = f"[{timestamp}] {msg}"
    state.logs.append(full_msg)
    sys.stdout.write(full_msg + "\n")
    sys.stdout.flush()


def create_task_record(count, threads):
    ensure_export_dir()
    ensure_backup_dirs()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    task_id = f"{stamp}_{suffix}"
    task = {
        "task_id": task_id,
        "started_at": now_str(),
        "ended_at": "",
        "target_count": count,
        "threads": threads,
        "stop_on_success": state.stop_on_success,
        "success_count": 0,
        "failed_count": 0,
        "status": "running",
        "raw_filename": f"accounts_{task_id}.json",
        "meta_filename": f"accounts_{task_id}.meta.json",
    }
    write_json_file(EXPORT_DIR / task["raw_filename"], [])
    write_json_file(EXPORT_DIR / task["meta_filename"], task)
    return task


def save_current_task_meta():
    if state.current_task:
        write_json_file(EXPORT_DIR / state.current_task["meta_filename"], state.current_task)


def get_task_data(task):
    if not task:
        return []
    return read_json_file(get_export_file_path(task["raw_filename"]), [])


def build_custom_export(records):
    custom_records = []
    for item in records:
        email = item.get("email") or item.get("original_email", "unknown")
        password = item.get("password") or item.get("original_password", "******")
        session_token = item.get("sessionToken") or "None"
        api_key = item.get("apiKey") or "None"
        custom_records.append(
            {
                "id": f"windsurf_{''.join(random.choices('0123456789abcdef', k=32))}",
                "github_login": email.split("@")[0],
                "github_id": random.randint(10**18, 9 * 10**18),
                "github_email": email,
                "github_access_token": session_token,
                "github_token_type": "Bearer",
                "copilot_token": session_token,
                "copilot_plan": "Free",
                "copilot_chat_enabled": True,
                "copilot_quota_snapshots": {
                    "windsurfCurrentUser": None,
                    "windsurfPlanInfo": {
                        "billingStrategy": "BILLING_STRATEGY_QUOTA",
                        "planName": "Free",
                        "monthlyFlowCredits": 500,
                        "monthlyPromptCredits": 2500,
                    },
                    "windsurfPlanStatus": {
                        "availableFlowCredits": 500,
                        "availablePromptCredits": 2500,
                        "dailyQuotaRemainingPercent": 100,
                    },
                },
                "original_email": email,
                "original_password": password,
                "windsurf_api_key": api_key,
            }
        )
    return custom_records


def build_session_token_lines(records):
    lines = []
    for item in records:
        token = (
            item.get("sessionToken")
            or item.get("copilot_token")
            or item.get("github_access_token")
            or ""
        )
        token = str(token).strip()
        if token and token != "None":
            lines.append(token)
    return lines


def append_result_to_exports(result):
    ensure_export_dir()
    ensure_backup_dirs()
    with state.file_lock:
        if state.current_task:
            raw_path = EXPORT_DIR / state.current_task["raw_filename"]
            task_records = read_json_file(raw_path, [])
            task_records.append(result)
            write_json_file(raw_path, task_records)
            state.current_task["success_count"] = len(task_records)
            state.current_task["failed_count"] = state.failed_count
            save_current_task_meta()
            append_jsonl(
                JOURNAL_DIR / f"task_{state.current_task['task_id']}.jsonl",
                {"saved_at": now_str(), "result": result},
            )

        all_records = read_json_file(ALL_ACCOUNTS_FILE, [])
        all_records.append(result)
        write_json_file(ALL_ACCOUNTS_FILE, all_records)
        append_jsonl(JOURNAL_DIR / "accounts_all.jsonl", {"saved_at": now_str(), "result": result})


def finalize_current_task(status):
    if state.current_task:
        state.current_task["status"] = status
        state.current_task["ended_at"] = now_str()
        state.current_task["success_count"] = state.completed_count
        state.current_task["failed_count"] = state.failed_count
        save_current_task_meta()
        raw_path = EXPORT_DIR / state.current_task["raw_filename"]
        snapshot_json_file(raw_path, state.current_task["task_id"])
        snapshot_json_file(ALL_ACCOUNTS_FILE, "accounts_all")


def get_task_meta_by_id(task_id):
    ensure_export_dir()
    for meta_path in EXPORT_DIR.glob("*.meta.json"):
        meta = read_json_file(meta_path, None)
        if meta and meta.get("task_id") == task_id:
            return meta
    for task in get_recent_task_exports(days=3650):
        if task.get("task_id") == task_id:
            return task
    return None


def get_latest_task_meta():
    tasks = get_recent_task_exports(days=3650)
    return tasks[0] if tasks else None


def get_recent_task_exports(days=7):
    ensure_export_dir()
    cutoff = datetime.now() - timedelta(days=days)
    tasks = []
    seen_raw_filenames = set()

    for meta_path in EXPORT_DIR.glob("*.meta.json"):
        meta = read_json_file(meta_path, None)
        if not meta:
            continue
        try:
            started_at = datetime.strptime(meta.get("started_at", ""), "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        if started_at < cutoff:
            continue
        raw_records = read_json_file(get_export_file_path(meta["raw_filename"]), [])
        meta["success_count"] = len(raw_records)
        meta["download_url"] = f"exports/download?task_id={meta['task_id']}&format=raw"
        meta["custom_download_url"] = f"exports/download?task_id={meta['task_id']}&format=custom"
        meta["session_download_url"] = f"exports/download?task_id={meta['task_id']}&format=session"
        tasks.append(meta)
        seen_raw_filenames.add(meta["raw_filename"])

    for legacy_path in Path(".").glob("accounts_*.json"):
        if legacy_path.name == "accounts_all.json" or legacy_path.name in seen_raw_filenames:
            continue
        match = re.fullmatch(r"accounts_(\d{4}-\d{2}-\d{2})\.json", legacy_path.name)
        if not match:
            continue
        try:
            started_at = datetime.strptime(f"{match.group(1)} 00:00:00", "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        if started_at < cutoff:
            continue
        raw_records = read_json_file(legacy_path, [])
        task_id = f"legacy_{match.group(1)}"
        tasks.append(
            {
                "task_id": task_id,
                "started_at": started_at.strftime("%Y-%m-%d 00:00:00"),
                "ended_at": started_at.strftime("%Y-%m-%d 23:59:59"),
                "target_count": len(raw_records),
                "threads": 0,
                "stop_on_success": False,
                "success_count": len(raw_records),
                "failed_count": 0,
                "status": "legacy",
                "raw_filename": legacy_path.name,
                "meta_filename": "",
                "download_url": f"exports/download?task_id={task_id}&format=raw",
                "custom_download_url": f"exports/download?task_id={task_id}&format=custom",
                "session_download_url": f"exports/download?task_id={task_id}&format=session",
            }
        )

    tasks.sort(key=lambda item: item.get("started_at", ""), reverse=True)
    return tasks


def get_backup_items(limit=50):
    ensure_backup_dirs()
    items = []
    candidate_paths = [
        ALL_ACCOUNTS_FILE,
        Path("accounts_all.recovered.json"),
        Path("accounts_recovery_summary.json"),
        Path("cockpit_direct_import.fixed.json"),
    ]
    candidate_paths.extend(sorted(SNAPSHOT_DIR.glob("*"), reverse=True))
    candidate_paths.extend(sorted(JOURNAL_DIR.glob("*"), reverse=True))

    seen = set()
    for path in candidate_paths:
        if not path.exists():
            continue
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        stat = path.stat()
        items.append(
            {
                "name": path.name,
                "path": key,
                "size": stat.st_size,
                "updated_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "download_url": f"backups/download?path={path.as_posix()}",
            }
        )
        if len(items) >= limit:
            break
    return items


class TempMail:
    PROVIDERS = [
        {"kind": "mailtm", "base": "https://api.mail.tm"},
        {"kind": "mailtm", "base": "https://api.mail.gw"},
        {"kind": "1secmail", "base": "https://www.1secmail.com/api/v1/"},
        {"kind": "1secmail", "base": "https://www.1secmail.net/api/v1/"},
    ]
    PROVIDER_HEALTH = {}
    PROVIDER_HEALTH_LOCK = threading.Lock()

    def __init__(self, proxies):
        self.s = get_session(proxies)
        self.ua = random.choice(USER_AGENTS)
        self.s.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": self.ua,
            }
        )
        self.provider = None
        self.provider_kind = None
        self.api_base = None
        self.address = None
        self.password = None
        self.token = None
        self.login = None
        self.domain = None
        self.direct_mode = False

    def _fallback_to_direct(self, reason):
        if self.direct_mode:
            return
        self.direct_mode = True
        self.s.proxies.clear()
        add_log(f"[TempMail] Proxy unavailable, switched to direct mode: {reason}")

    def _pick_provider_order(self):
        now_ts = time.time()
        with self.PROVIDER_HEALTH_LOCK:
            available = []
            cooling = []
            for provider in self.PROVIDERS:
                stats = self.PROVIDER_HEALTH.get(provider["base"], {})
                cooldown_until = stats.get("cooldown_until", 0)
                if cooldown_until > now_ts:
                    cooling.append(provider)
                else:
                    available.append(provider)
        random.shuffle(available)
        if available:
            return available
        random.shuffle(cooling)
        return cooling

    def _mark_provider_success(self, provider_base):
        with self.PROVIDER_HEALTH_LOCK:
            self.PROVIDER_HEALTH[provider_base] = {
                "fails": 0,
                "cooldown_until": 0,
                "last_error": "",
                "updated_at": now_str(),
            }

    def _mark_provider_failure(self, provider_base, error_message):
        msg = str(error_message)
        cooldown_seconds = 15
        if "429" in msg:
            cooldown_seconds = 45
        elif "403" in msg:
            cooldown_seconds = 600
        elif "CERTIFICATE_VERIFY_FAILED" in msg or "Hostname mismatch" in msg:
            cooldown_seconds = 3600

        with self.PROVIDER_HEALTH_LOCK:
            prev = self.PROVIDER_HEALTH.get(provider_base, {})
            fails = int(prev.get("fails", 0)) + 1
            extra = 0
            if fails >= 3:
                extra = 30
            if fails >= 6:
                extra = 120
            if fails >= 10:
                extra = 300
            self.PROVIDER_HEALTH[provider_base] = {
                "fails": fails,
                "cooldown_until": time.time() + cooldown_seconds + extra,
                "last_error": msg[:200],
                "updated_at": now_str(),
            }

    def _create_mailtm_account(self, max_retries):
        for attempt in range(max_retries):
            if state.should_stop:
                return None
            try:
                add_log(f"[TempMail:{self.api_base}] Fetching domain ({attempt + 1}/{max_retries})...")
                response = self.s.get(f"{self.api_base}/domains", timeout=15)
                response.raise_for_status()
                data = response.json()
                domains = data if isinstance(data, list) else data.get("hydra:member", data.get("member", []))
                if not domains:
                    raise RuntimeError("No available temp-mail domain found")

                self.domain = domains[0].get("domain")
                self.login = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
                self.address = f"{self.login}@{self.domain}"
                self.password = "".join(random.choices(string.ascii_letters + string.digits, k=12))

                response = self.s.post(
                    f"{self.api_base}/accounts",
                    json={"address": self.address, "password": self.password},
                    timeout=10,
                )
                response.raise_for_status()
                response = self.s.post(
                    f"{self.api_base}/token",
                    json={"address": self.address, "password": self.password},
                    timeout=10,
                )
                response.raise_for_status()
                self.token = response.json()["token"]
                self.s.headers.update({"Authorization": f"Bearer {self.token}"})
                self._mark_provider_success(self.api_base)
                add_log(f"[TempMail:{self.api_base}] Created temp mailbox: {self.address}")
                return self.address
            except Exception as e:
                if should_fallback_direct(e):
                    self._fallback_to_direct(e)
                self._mark_provider_failure(self.api_base, e)
                add_log(f"[TempMail:{self.api_base}] Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
        return None

    def _create_1secmail_account(self, max_retries):
        for attempt in range(max_retries):
            if state.should_stop:
                return None
            try:
                add_log(f"[TempMail:{self.api_base}] Fetching domain ({attempt + 1}/{max_retries})...")
                response = self.s.get(f"{self.api_base}?action=getDomainList", timeout=15)
                response.raise_for_status()
                domains = response.json() or []
                if not domains:
                    raise RuntimeError("No available 1secmail domain found")
                self.domain = random.choice(domains)
                self.login = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
                self.address = f"{self.login}@{self.domain}"
                self.password = "".join(random.choices(string.ascii_letters + string.digits, k=12))
                self._mark_provider_success(self.api_base)
                add_log(f"[TempMail:{self.api_base}] Created temp mailbox: {self.address}")
                return self.address
            except Exception as e:
                if should_fallback_direct(e):
                    self._fallback_to_direct(e)
                self._mark_provider_failure(self.api_base, e)
                add_log(f"[TempMail:{self.api_base}] Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
        return None

    def create_account(self, max_retries=3):
        per_provider_retries = 1
        for provider in self._pick_provider_order():
            if state.should_stop:
                return None
            self.provider = provider
            self.provider_kind = provider["kind"]
            self.api_base = provider["base"]
            if self.provider_kind == "mailtm":
                email = self._create_mailtm_account(per_provider_retries)
            elif self.provider_kind == "1secmail":
                email = self._create_1secmail_account(per_provider_retries)
            else:
                email = None
            if email:
                return email
            add_log(f"[TempMail] Provider switched after failure: {self.api_base}")
        return None

    def wait_for_code(self, timeout=60):
        add_log(f"[TempMail:{self.api_base}] Waiting for verification code...")
        start_at = time.time()
        while time.time() - start_at < timeout:
            if state.should_stop:
                return None
            try:
                if self.provider_kind == "mailtm":
                    response = self.s.get(f"{self.api_base}/messages", timeout=10)
                    response.raise_for_status()
                    data = response.json()
                    messages = data if isinstance(data, list) else data.get("hydra:member", data.get("member", []))
                elif self.provider_kind == "1secmail":
                    response = self.s.get(
                        f"{self.api_base}?action=getMessages&login={self.login}&domain={self.domain}",
                        timeout=10,
                    )
                    response.raise_for_status()
                    messages = response.json() or []
                else:
                    messages = []

                for message in messages:
                    message_id = message.get("id") if isinstance(message, dict) else None
                    if not message_id:
                        continue
                    if self.provider_kind == "mailtm":
                        message_response = self.s.get(f"{self.api_base}/messages/{message_id}", timeout=10)
                    else:
                        message_response = self.s.get(
                            f"{self.api_base}?action=readMessage&login={self.login}&domain={self.domain}&id={message_id}",
                            timeout=10,
                        )
                    message_response.raise_for_status()
                    message_data = message_response.json()
                    content = (
                        message_data.get("textBody", "")
                        or message_data.get("text", "")
                        or message_data.get("body", "")
                        or message_data.get("intro", "")
                    )
                    match = re.search(r"\b(\d{6})\b", content)
                    if match:
                        code = match.group(1)
                        add_log(f"[TempMail:{self.api_base}] Verification code received: {code}")
                        return code
            except Exception:
                # Some environments temporarily lose local proxy; keep polling in direct mode.
                # We avoid raising here to preserve original wait behavior.
                pass
            time.sleep(2)
        return None


class WindsurfReplay:
    def __init__(self, proxies):
        self.s = get_session(proxies)
        self.ua = random.choice(USER_AGENTS)
        self.headers = {
            "Accept": "*/*",
            "Origin": BASE,
            "Referer": f"{BASE}/account/register",
            "User-Agent": self.ua,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        self.direct_mode = False

    def _fallback_to_direct(self, reason):
        if self.direct_mode:
            return
        self.direct_mode = True
        self.s.proxies.clear()
        add_log(f"[Windsurf] Proxy unavailable, switched to direct mode: {reason}")

    def _post(self, path, payload, extra=None):
        headers = dict(self.headers)
        if extra:
            headers.update(extra)
        try:
            return self.s.post(f"{BASE}{path}", headers=headers, json=payload, timeout=20)
        except Exception as e:
            if should_fallback_direct(e):
                self._fallback_to_direct(e)
                return self.s.post(f"{BASE}{path}", headers=headers, json=payload, timeout=20)
            raise

    def _post_full_url(self, url, payload, headers):
        try:
            return self.s.post(url, headers=headers, json=payload, timeout=20)
        except Exception as e:
            if should_fallback_direct(e):
                self._fallback_to_direct(e)
                return self.s.post(url, headers=headers, json=payload, timeout=20)
            raise

    def register_flow(self, email, password, name, temp_mail):
        try:
            add_log("[Windsurf] Step 1/4: Requesting email verification...")
            response = self._post(
                "/_devin-auth/email/start",
                {"email": email, "mode": "signup", "product": "Windsurf"},
            )
            response.raise_for_status()
            verification_token = response.json()["email_verification_token"]

            code = temp_mail.wait_for_code()
            if not code:
                raise RuntimeError("Verification code wait timed out")

            add_log("[Windsurf] Step 2/4: Submitting signup form...")
            response = self._post_full_url(
                f"{BASE}/_devin-auth/email/complete",
                {
                    "email_verification_token": verification_token,
                    "code": code,
                    "mode": "signup",
                    "password": password,
                    "name": name,
                },
                self.headers,
            )
            response.raise_for_status()
            auth1_token = response.json()["token"]

            add_log("[Windsurf] Step 3/4: Initializing session...")
            response = self.s.post(
                f"{BASE}/_backend/exa.seat_management_pb.SeatManagementService/WindsurfPostAuth",
                headers={
                    "connect-protocol-version": "1",
                    "x-devin-auth1-token": auth1_token,
                    **self.headers,
                },
                json={},
                timeout=20,
            )
            response.raise_for_status()
            result = response.json()
            session_token = result["sessionToken"]
            account_id = result["accountId"]
            org_id = result["primaryOrgId"]

            add_log("[Windsurf] Step 4/4: Fetching API key and callback token...")
            time.sleep(3)
            authed_headers = {
                **self.headers,
                "connect-protocol-version": "1",
                "x-auth-token": session_token,
                "x-devin-session-token": session_token,
                "x-devin-auth1-token": auth1_token,
                "x-devin-account-id": account_id,
                "x-devin-primary-org-id": org_id,
            }

            api_key = "None"
            ott = "None"
            callback_url = "None"
            try:
                user_response = self._post_full_url(
                    f"{BASE}/_backend/exa.seat_management_pb.SeatManagementService/GetCurrentUser",
                    {"generateProfilePictureUrl": True, "includeSubscription": True},
                    authed_headers,
                )
                api_key = user_response.json().get("user", {}).get("apiKey", "None")

                ott_response = self._post_full_url(
                    f"{BASE}/_backend/exa.seat_management_pb.SeatManagementService/GetOneTimeAuthToken",
                    {},
                    authed_headers,
                )
                ott = ott_response.json().get("authToken", "None")
                if ott != "None":
                    callback_url = (
                        "http://127.0.0.1:58123/windsurf-auth-callback"
                        "?state=FozSkD1xVWMuUcbRbiwhMI7c7-mSGY_1"
                        f"&access_token={ott}"
                    )
            except Exception as e:
                add_log(f"[Windsurf] Extra token fetch failed: {e}")

            add_log(f"[Windsurf] Registration complete: {email}")
            return {
                "email": email,
                "password": password,
                "apiKey": api_key,
                "sessionToken": session_token,
                "ott": ott,
                "callbackUrl": callback_url,
                "timestamp": now_str(),
            }
        except requests.exceptions.Timeout:
            add_log("[Windsurf] Request timeout")
            raise
        except Exception as e:
            add_log(f"[Windsurf] Registration failed: {e}")
            raise


def single_registration_worker(worker_id):
    if state.should_stop:
        return
    if state.stop_on_success and state.completed_count >= state.total_to_register:
        return

    state.active_threads += 1
    add_log(f"[Worker-{worker_id}] Started")
    try:
        password = "".join(random.choices(string.ascii_letters + string.digits, k=16))
        name = "User " + "".join(random.choices(string.ascii_uppercase, k=5))
        temp_mail = TempMail(state.proxies)
        email = temp_mail.create_account()
        if not email:
            state.failed_count += 1
            return

        replay = WindsurfReplay(state.proxies)
        result = replay.register_flow(email, password, name, temp_mail)
        append_result_to_exports(result)

        state.completed_count += 1
        if state.stop_on_success and state.completed_count >= state.total_to_register:
            state.should_stop = True
            add_log("[Task] Target reached, stopping remaining workers...")

        add_log(f"[Worker-{worker_id}] Done ({state.completed_count}/{state.total_to_register})")
    except Exception as e:
        state.failed_count += 1
        if state.current_task:
            state.current_task["failed_count"] = state.failed_count
            save_current_task_meta()
        add_log(f"[Worker-{worker_id}] Failed: {e}")
    finally:
        state.active_threads -= 1
        if state.active_threads == 0:
            state.is_running = False
            was_stopped = state.should_stop and state.completed_count < state.total_to_register
            state.should_stop = False
            finalize_current_task("stopped" if was_stopped else "completed")
            add_log(f"[Task] Finished. Success={state.completed_count}, Failed={state.failed_count}")


def batch_registration_manager(count, threads):
    state.is_running = True
    state.should_stop = False
    state.total_to_register = count
    state.completed_count = 0
    state.failed_count = 0
    state.start_time = time.time()
    state.current_task = create_task_record(count, threads)

    mode_label = "success-target" if state.stop_on_success else "attempt-limit"
    add_log(f"[Task] Started. Mode={mode_label}, Count={count}, Threads={threads}")

    semaphore = threading.Semaphore(threads)

    def worker_wrapper(task_no):
        with semaphore:
            if not state.should_stop:
                single_registration_worker(task_no)

    task_no = 1
    while not state.should_stop:
        if not state.stop_on_success and task_no > count:
            break
        if state.stop_on_success and state.completed_count >= count:
            break
        if state.active_threads < threads:
            t = threading.Thread(target=worker_wrapper, args=(task_no,))
            t.daemon = True
            t.start()
            task_no += 1
            time.sleep(0.1)
        else:
            time.sleep(0.5)

    while state.active_threads > 0:
        time.sleep(1)

    state.is_running = False


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/status")
def get_status():
    new_logs = state.logs[state.last_log_index :]
    state.last_log_index = len(state.logs)
    if state.is_running and state.start_time:
        elapsed_hours = (time.time() - state.start_time) / 3600
        if elapsed_hours > 0:
            state.success_per_hour = round(state.completed_count / elapsed_hours, 2)
    return jsonify(
        {
            "is_running": state.is_running,
            "active_threads": state.active_threads,
            "success_count": state.completed_count,
            "failed_count": state.failed_count,
            "completed_count": state.completed_count,
            "total_count": state.total_to_register,
            "success_per_hour": state.success_per_hour,
            "new_logs": new_logs,
            "current_task": state.current_task,
        }
    )


@app.route("/accounts")
def get_accounts():
    task = state.current_task or get_latest_task_meta()
    return jsonify(get_task_data(task))


@app.route("/exports")
def get_exports():
    return jsonify(get_recent_task_exports(days=7))


@app.route("/backups")
def get_backups():
    return jsonify(get_backup_items())


@app.route("/clear_today", methods=["POST"])
def clear_today():
    if state.is_running:
        return jsonify({"status": "error", "message": "Task is still running"}), 400

    today = datetime.now().strftime("%Y-%m-%d")
    removed = 0
    ensure_export_dir()
    for meta_path in EXPORT_DIR.glob("*.meta.json"):
        meta = read_json_file(meta_path, None)
        if not meta or not meta.get("started_at", "").startswith(today):
            continue
        raw_path = EXPORT_DIR / meta["raw_filename"]
        if raw_path.exists():
            raw_path.unlink()
        meta_path.unlink(missing_ok=True)
        removed += 1

    state.completed_count = 0
    state.failed_count = 0
    state.current_task = None
    return jsonify({"status": "ok", "removed_tasks": removed})


@app.route("/start_batch", methods=["POST"])
def start_batch_task():
    if state.is_running:
        return jsonify({"status": "error", "message": "Task already running"}), 400

    data = request.json or {}
    try:
        count = int(data.get("count", 1))
        threads = int(data.get("threads", 1))
        state.stop_on_success = bool(data.get("stop_on_success", False))
        state.export_custom_format = bool(data.get("export_custom_format", False))
        threading.Thread(target=batch_registration_manager, args=(count, threads), daemon=True).start()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/stop", methods=["POST"])
def stop_tasks():
    state.should_stop = True
    add_log("[Task] Stop signal sent")
    return jsonify({"status": "ok"})


@app.route("/config", methods=["POST"])
def update_config():
    data = request.json or {}
    state.proxies["http"] = str(data.get("http", state.proxies["http"])).strip()
    state.proxies["https"] = str(data.get("https", state.proxies["https"])).strip()
    save_runtime_config()
    add_log("[Config] Proxy settings updated")
    return jsonify({"status": "ok"})


@app.route("/config", methods=["GET"])
def get_config():
    return jsonify(
        {
            "http": state.proxies.get("http", ""),
            "https": state.proxies.get("https", ""),
        }
    )


@app.route("/download")
def download_latest():
    latest_task = get_latest_task_meta()
    if not latest_task:
        return "No exports found", 404
    fmt = request.args.get("format", "raw")
    return _send_task_export(latest_task, fmt)


@app.route("/exports/download")
def download_task_export():
    task_id = request.args.get("task_id", "")
    fmt = request.args.get("format", "raw")
    task = get_task_meta_by_id(task_id)
    if not task:
        return "Task not found", 404
    return _send_task_export(task, fmt)


@app.route("/backups/download")
def download_backup_file():
    raw_path = request.args.get("path", "").strip()
    if not raw_path:
        return "Missing path", 400
    path = Path(raw_path)
    allowed_roots = [Path("."), BACKUP_DIR]
    resolved = path.resolve()
    if not any(root.resolve() in resolved.parents or resolved == root.resolve() for root in allowed_roots):
        return "Invalid path", 400
    if not resolved.exists() or not resolved.is_file():
        return "File not found", 404
    return send_file(resolved, as_attachment=True, download_name=resolved.name)


def _send_task_export(task, fmt):
    raw_path = EXPORT_DIR / task["raw_filename"]
    raw_path = get_export_file_path(task["raw_filename"])
    if not raw_path.exists():
        return "Export file missing", 404

    records = read_json_file(raw_path, [])
    if fmt == "custom":
        custom_records = build_custom_export(records)
        mem_file = io.BytesIO()
        mem_file.write(json.dumps(custom_records, indent=2, ensure_ascii=False).encode("utf-8"))
        mem_file.seek(0)
        filename = f"cockpit_export_{task['task_id']}.json"
        return send_file(mem_file, mimetype="application/json", as_attachment=True, download_name=filename)
    if fmt == "session":
        session_lines = build_session_token_lines(records)
        mem_file = io.BytesIO()
        mem_file.write(("\n".join(session_lines) + ("\n" if session_lines else "")).encode("utf-8"))
        mem_file.seek(0)
        filename = f"devin_session_tokens_{task['task_id']}.txt"
        return send_file(mem_file, mimetype="text/plain", as_attachment=True, download_name=filename)

    return send_file(raw_path, mimetype="application/json", as_attachment=True, download_name=task["raw_filename"])


if __name__ == "__main__":
    ensure_export_dir()
    ensure_backup_dirs()
    load_runtime_config()
    add_log("Starting web service on http://127.0.0.1:5000")
    app.run(host="0.0.0.0", debug=False, port=5000)
