import json
import os
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic_settings import BaseSettings, SettingsConfigDict


try:
    # pyzk supports ZKTeco comm-key (communications password) scrambling/auth internally.
    from zk import ZK  # type: ignore
except Exception:  # pragma: no cover
    ZK = None  # type: ignore


@dataclass(frozen=True)
class PollerConfig:
    device_ip: str
    device_port: int
    comm_key: int
    terminal_sn: str
    webhook_url: str
    webhook_secret: str
    poll_seconds: int
    lookback_seconds: int
    state_file: Path


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _env_str(name: str, default: str = "") -> str:
    v = os.getenv(name, default)
    return v.strip() if isinstance(v, str) else default


def _load_state(state_file: Path) -> dict[str, Any]:
    try:
        if state_file.exists():
            return json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(state_file: Path, state: dict[str, Any]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _dt_to_epoch_ms(dt: datetime) -> int:
    # pyzk typically returns naive datetime interpreted as local time.
    # `timestamp()` converts naive datetimes using the local timezone on this machine.
    return int(dt.timestamp() * 1000)


def _attendance_to_webhook_payload(terminal_sn: str, att: Any) -> tuple[str, dict[str, Any], int]:
    # pyzk Attendance has: user_id, timestamp, status, punch
    emp_code = str(att.user_id)
    punch_time_ms = _dt_to_epoch_ms(att.timestamp)
    event_type = "clock_in" if int(att.status) == 0 else "clock_out"

    payload = {
        "terminal_sn": terminal_sn,
        "emp_code": emp_code,
        "event_type": event_type,
        "punch_time": punch_time_ms,
    }
    # Return punch_time_ms separately for easy filtering/updating.
    return event_type, payload, punch_time_ms


def _post_json(url: str, payload: dict[str, Any], secret: str) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
    }
    if secret:
        headers["X-ZKTeco-Secret"] = secret

    req = Request(url, data=data, headers=headers, method="POST")
    with urlopen(req, timeout=15) as resp:
        # Read and ignore response; we only care about whether it succeeded (2xx).
        resp.read()


def _run_once(cfg: PollerConfig, last_sync_ms: int) -> int:
    if ZK is None:
        raise RuntimeError("pyzk is not installed. Run: pip install -r requirements.txt")

    zk = ZK(
        cfg.device_ip,
        port=cfg.device_port,
        timeout=60,
        password=cfg.comm_key,
    )

    conn = None
    try:
        conn = zk.connect()
        attendances = conn.get_attendance()
        conn.disconnect()
    except Exception:
        # Ensure we attempt disconnect even if something went wrong.
        try:
            if conn is not None:
                conn.disconnect()
        except Exception:
            pass
        raise

    # Filter by lookback window to avoid re-sending too aggressively.
    # We still rely on GSPS unique constraint to prevent duplicates.
    min_ms = max(0, last_sync_ms - (cfg.lookback_seconds * 1000))

    max_seen_ms = last_sync_ms
    for att in attendances:
        _event_type, payload, punch_time_ms = _attendance_to_webhook_payload(cfg.terminal_sn, att)
        if punch_time_ms < min_ms:
            continue

        _post_json(cfg.webhook_url, payload, cfg.webhook_secret)
        max_seen_ms = max(max_seen_ms, punch_time_ms)

    return max_seen_ms


def build_config() -> PollerConfig:
    class PollerSettings(BaseSettings):
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
        )

        ZKTECO_POLLER_DEVICE_IP: str = ""
        ZKTECO_POLLER_DEVICE_PORT: int = 4370
        ZKTECO_POLLER_COMM_KEY: int = 0
        ZKTECO_POLLER_TERMINAL_SN: str = ""

        ZKTECO_POLLER_WEBHOOK_URL: str = ""
        ZKTECO_WEBHOOK_SECRET: str = ""

        ZKTECO_POLLER_POLL_SECONDS: int = 60
        ZKTECO_POLLER_LOOKBACK_SECONDS: int = 600
        ZKTECO_POLLER_STATE_DIR: str = "data"

    s = PollerSettings()

    if not s.ZKTECO_POLLER_DEVICE_IP:
        raise RuntimeError("Missing env: ZKTECO_POLLER_DEVICE_IP")
    if not s.ZKTECO_POLLER_TERMINAL_SN:
        raise RuntimeError("Missing env: ZKTECO_POLLER_TERMINAL_SN (must match GSPS terminal_sn)")
    if not s.ZKTECO_POLLER_WEBHOOK_URL:
        raise RuntimeError("Missing env: ZKTECO_POLLER_WEBHOOK_URL")

    device_ip = s.ZKTECO_POLLER_DEVICE_IP
    terminal_sn = s.ZKTECO_POLLER_TERMINAL_SN
    webhook_url = s.ZKTECO_POLLER_WEBHOOK_URL

    webhook_secret = s.ZKTECO_WEBHOOK_SECRET

    poll_seconds = s.ZKTECO_POLLER_POLL_SECONDS
    lookback_seconds = s.ZKTECO_POLLER_LOOKBACK_SECONDS

    state_dir = Path(s.ZKTECO_POLLER_STATE_DIR)
    state_file = state_dir / f"zkteco_poller_state_{terminal_sn}.json"

    return PollerConfig(
        device_ip=device_ip,
        device_port=s.ZKTECO_POLLER_DEVICE_PORT,
        comm_key=s.ZKTECO_POLLER_COMM_KEY,
        terminal_sn=terminal_sn,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
        poll_seconds=poll_seconds,
        lookback_seconds=lookback_seconds,
        state_file=state_file,
    )


def main() -> None:
    cfg = build_config()
    state = _load_state(cfg.state_file)
    last_sync_ms = int(state.get("last_sync_ms", 0) or 0)

    print(f"[zkteco_poller] Start terminal_sn={cfg.terminal_sn} device={cfg.device_ip}:{cfg.device_port}")
    if cfg.comm_key:
        print("[zkteco_poller] comm_key is non-zero; pyzk will authenticate with comm-key.")

    while True:
        try:
            max_seen_ms = _run_once(cfg, last_sync_ms)
            last_sync_ms = max_seen_ms
            state = {
                "terminal_sn": cfg.terminal_sn,
                "device_ip": cfg.device_ip,
                "last_sync_ms": last_sync_ms,
                "updated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            _save_state(cfg.state_file, state)
            print(f"[zkteco_poller] synced through {datetime.fromtimestamp(last_sync_ms/1000, tz=timezone.utc).isoformat()}")
        except (HTTPError, URLError) as e:
            print(f"[zkteco_poller] network error: {e}")
        except Exception as e:
            print(f"[zkteco_poller] error: {e}")
            traceback.print_exc()

        time.sleep(cfg.poll_seconds)


if __name__ == "__main__":
    main()

