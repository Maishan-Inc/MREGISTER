import json
import os
import threading
from datetime import datetime, timedelta, timezone

from .utils import decode_jwt_payload

_file_lock = threading.Lock()


class TokenManager:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.token_dir = os.path.join(output_dir, "tokens")
        self.accounts_file = os.path.join(output_dir, "accounts.txt")
        self.ak_file = os.path.join(output_dir, "ak.txt")
        self.rk_file = os.path.join(output_dir, "rk.txt")
        os.makedirs(self.token_dir, exist_ok=True)

    def save_account(self, email, password):
        with _file_lock:
            with open(self.accounts_file, "a", encoding="utf-8") as handle:
                handle.write(f"{email}----{password}\n")

    def save_tokens(self, email, tokens):
        access_token = tokens.get("access_token", "")
        refresh_token = tokens.get("refresh_token", "")
        id_token = tokens.get("id_token", "")

        if access_token:
            with _file_lock:
                with open(self.ak_file, "a", encoding="utf-8") as handle:
                    handle.write(f"{access_token}\n")

        if refresh_token:
            with _file_lock:
                with open(self.rk_file, "a", encoding="utf-8") as handle:
                    handle.write(f"{refresh_token}\n")

        if not access_token:
            return

        payload = decode_jwt_payload(access_token)
        auth_info = payload.get("https://api.openai.com/auth", {})
        account_id = auth_info.get("chatgpt_account_id", "")

        expired_str = ""
        exp_timestamp = payload.get("exp")
        if isinstance(exp_timestamp, int) and exp_timestamp > 0:
            exp_dt = datetime.fromtimestamp(exp_timestamp, tz=timezone(timedelta(hours=8)))
            expired_str = exp_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")

        now = datetime.now(tz=timezone(timedelta(hours=8)))
        token_data = {
          "type": "codex",
          "email": email,
          "expired": expired_str,
          "id_token": id_token,
          "account_id": account_id,
          "access_token": access_token,
          "last_refresh": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
          "refresh_token": refresh_token,
        }
        token_path = os.path.join(self.token_dir, f"{email}.json")
        with _file_lock:
            with open(token_path, "w", encoding="utf-8") as handle:
                json.dump(token_data, handle, ensure_ascii=False, indent=2)
