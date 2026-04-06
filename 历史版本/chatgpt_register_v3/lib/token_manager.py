"""
Token 管理模块 - 保存和上传 Token
"""

import os
import json
import threading
from datetime import datetime, timezone, timedelta

from .utils import decode_jwt_payload


# 全局文件锁
_file_lock = threading.Lock()


class TokenManager:
    """Token 管理器"""

    def __init__(self, config):
        """
        初始化 Token 管理器
        
        Args:
            config: 配置字典
        """
        self.ak_file = config.get("ak_file", "ak.txt")
        self.rk_file = config.get("rk_file", "rk.txt")
        self.token_json_dir = config.get("token_json_dir", "tokens")
        self.upload_api_url = config.get("upload_api_url", "")
        self.upload_api_token = config.get("upload_api_token", "")
        
        # 确保 token 目录存在
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.token_dir = self.token_json_dir if os.path.isabs(self.token_json_dir) else os.path.join(base_dir, self.token_json_dir)
        os.makedirs(self.token_dir, exist_ok=True)

    def save_tokens(self, email, tokens):
        """
        保存 tokens 到所有目标（txt + JSON + 上传）
        
        Args:
            email: 邮箱地址
            tokens: token 字典，包含 access_token, refresh_token, id_token
        """
        access_token = tokens.get("access_token", "")
        refresh_token = tokens.get("refresh_token", "")
        id_token = tokens.get("id_token", "")

        # 保存到 ak.txt
        if access_token:
            with _file_lock:
                with open(self.ak_file, "a", encoding="utf-8") as f:
                    f.write(f"{access_token}\n")

        # 保存到 rk.txt
        if refresh_token:
            with _file_lock:
                with open(self.rk_file, "a", encoding="utf-8") as f:
                    f.write(f"{refresh_token}\n")

        if not access_token:
            return

        # 解析 JWT payload
        payload = decode_jwt_payload(access_token)
        auth_info = payload.get("https://api.openai.com/auth", {})
        account_id = auth_info.get("chatgpt_account_id", "")

        # 计算过期时间
        exp_timestamp = payload.get("exp")
        expired_str = ""
        if isinstance(exp_timestamp, int) and exp_timestamp > 0:
            exp_dt = datetime.fromtimestamp(exp_timestamp, tz=timezone(timedelta(hours=8)))
            expired_str = exp_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")

        # 构造 token 数据
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

        # 保存 JSON 文件
        token_path = os.path.join(self.token_dir, f"{email}.json")
        with _file_lock:
            with open(token_path, "w", encoding="utf-8") as f:
                json.dump(token_data, f, ensure_ascii=False, indent=2)

        # 上传到 CPA 管理平台（如果配置了）
        if self.upload_api_url:
            self._upload_token_json(token_path)

    def _upload_token_json(self, filepath):
        """上传 Token JSON 文件到 CPA 管理平台"""
        try:
            # 尝试使用 curl_cffi
            try:
                from curl_cffi import requests as curl_requests
                from curl_cffi import CurlMime
                
                filename = os.path.basename(filepath)
                mp = CurlMime()
                mp.addpart(
                    name="file",
                    content_type="application/json",
                    filename=filename,
                    local_path=filepath,
                )

                session = curl_requests.Session()
                resp = session.post(
                    self.upload_api_url,
                    multipart=mp,
                    headers={"Authorization": f"Bearer {self.upload_api_token}"},
                    verify=False,
                    timeout=30,
                )

                if resp.status_code == 200:
                    print(f"  [CPA] Token JSON 已上传到 CPA 管理平台")
                else:
                    print(f"  [CPA] 上传失败: {resp.status_code} - {resp.text[:200]}")
                
                mp.close()
                
            except ImportError:
                # 如果没有 curl_cffi，使用标准 requests
                import requests
                
                with open(filepath, 'rb') as f:
                    files = {'file': (os.path.basename(filepath), f, 'application/json')}
                    headers = {"Authorization": f"Bearer {self.upload_api_token}"}
                    
                    resp = requests.post(
                        self.upload_api_url,
                        files=files,
                        headers=headers,
                        verify=False,
                        timeout=30,
                    )
                    
                    if resp.status_code == 200:
                        print(f"  [CPA] Token JSON 已上传到 CPA 管理平台")
                    else:
                        print(f"  [CPA] 上传失败: {resp.status_code} - {resp.text[:200]}")
                        
        except Exception as e:
            print(f"  [CPA] 上传异常: {e}")

    def save_account(self, email, password, filepath="accounts.txt"):
        """
        保存账号信息
        
        Args:
            email: 邮箱
            password: 密码
            filepath: 保存文件路径
        """
        with _file_lock:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(f"{email}----{password}\n")
