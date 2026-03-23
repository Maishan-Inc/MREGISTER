import os, json, random, string, time, re, struct, argparse
import threading
import concurrent.futures
from pathlib import Path
from urllib.parse import urljoin, urlparse
from curl_cffi import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from email_service import EmailService
from YesCaptcha_service import TurnstileService

load_dotenv()

# 基础配置
site_url = "https://accounts.x.ai"
user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
PROXIES = {
    # "http": "http://127.0.0.1:10808",
    # "https": "http://127.0.0.1:10808"
}

# 动态获取的全局变量
config = {
    "site_key": "0x4AAAAAAAhr9JGVDZbrZOo0",
    "action_id": None,
    "state_tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22(app)%22%2C%7B%22children%22%3A%5B%22(auth)%22%2C%7B%22children%22%3A%5B%22sign-up%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Fsign-up%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D"
}

post_lock = threading.Lock()
file_lock = threading.Lock()
success_count = 0
start_time = time.time()
target_count = 0
stop_event = threading.Event()
output_dir = Path(__file__).parent.resolve()


def should_stop() -> bool:
    return stop_event.is_set() or (target_count > 0 and success_count >= target_count)


def keys_dir() -> Path:
    return output_dir / "keys"

def generate_random_name() -> str:
    length = random.randint(4, 6)
    return random.choice(string.ascii_uppercase) + ''.join(random.choice(string.ascii_lowercase) for _ in range(length - 1))

def generate_random_string(length: int = 15) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))

def encode_grpc_message(field_id, string_value):
    key = (field_id << 3) | 2
    value_bytes = string_value.encode('utf-8')
    length = len(value_bytes)
    payload = struct.pack('B', key) + struct.pack('B', length) + value_bytes
    return b'\x00' + struct.pack('>I', len(payload)) + payload

def encode_grpc_message_verify(email, code):
    p1 = struct.pack('B', (1 << 3) | 2) + struct.pack('B', len(email)) + email.encode('utf-8')
    p2 = struct.pack('B', (2 << 3) | 2) + struct.pack('B', len(code)) + code.encode('utf-8')
    payload = p1 + p2
    return b'\x00' + struct.pack('>I', len(payload)) + payload

def send_email_code_grpc(session, email):
    url = f"{site_url}/auth_mgmt.AuthManagement/CreateEmailValidationCode"
    data = encode_grpc_message(1, email)
    headers = {"content-type": "application/grpc-web+proto", "x-grpc-web": "1", "x-user-agent": "connect-es/2.1.1", "origin": site_url, "referer": f"{site_url}/sign-up?redirect=grok-com"}
    try:
        # print(f"[debug] {email} 正在发送验证码请求...")
        res = session.post(url, data=data, headers=headers, timeout=15)
        # print(f"[debug] {email} 请求结束，状态码: {res.status_code}")
        return res.status_code == 200
    except Exception as e:
        print(f"[-] {email} 发送验证码异常: {e}")
        return False

def verify_email_code_grpc(session, email, code):
    url = f"{site_url}/auth_mgmt.AuthManagement/VerifyEmailValidationCode"
    data = encode_grpc_message_verify(email, code)
    headers = {"content-type": "application/grpc-web+proto", "x-grpc-web": "1", "x-user-agent": "connect-es/2.1.1", "origin": site_url, "referer": f"{site_url}/sign-up?redirect=grok-com"}
    try:
        print(f"[debug] {email} 验证码: {code}, 状态码检查...")
        res = session.post(url, data=data, headers=headers, timeout=15)
        # print(f"[debug] {email} 验证响应状态: {res.status_code}, 内容长度: {len(res.content)}")
        return res.status_code == 200
    except Exception as e:
        print(f"[-] {email} 验证验证码异常: {e}")
        return False

def register_single_thread():
    # 错峰启动，防止瞬时并发过高
    time.sleep(random.uniform(0, 5))
    
    try:
        email_service = EmailService(proxies=PROXIES)
        turnstile_service = TurnstileService()
    except Exception as e:
        print(f"[-] 服务初始化失败: {e}")
        return
    
    # 从 config 获取 action_id，缺少则直接退出
    final_action_id = config.get("action_id")
    if not final_action_id:
        print("[-] 线程退出：缺少 Action ID")
        return
    
    while not should_stop():
        try:
            with requests.Session(impersonate="chrome120", proxies=PROXIES) as session:
                # 预热连接
                try: session.get(site_url, timeout=10)
                except: pass

                password = generate_random_string()
                
                # print(f"[debug] 线程-{threading.get_ident()} 正在请求创建邮箱...")
                try:
                    jwt, email = email_service.create_email()
                except Exception as e:
                    print(f"[-] 邮箱服务抛出异常: {e}")
                    jwt, email = None, None

                if not email:
                    print(f"[-] 线程-{threading.get_ident()} 邮箱创建返回空，可能接口挂了或超时，等待 5s...")
                    time.sleep(5); continue
                
                print(f"[*] 开始注册: {email}")

                # Step 1: 发送验证码
                if not send_email_code_grpc(session, email):
                    print(f"[-] {email} 发送验证码失败")
                    time.sleep(5); continue
                
                # Step 2: 获取验证码
                verify_code = None
                for _ in range(30):
                    time.sleep(1)
                    content = email_service.fetch_first_email(jwt)
                    if content:
                        match = re.search(r">([A-Z0-9]{3}-[A-Z0-9]{3})<", content)
                        if match:
                            verify_code = match.group(1).replace("-", "")
                            break
                if not verify_code:
                    print(f"[-] {email} 未收到验证码")
                    continue

                # Step 3: 验证验证码
                if not verify_email_code_grpc(session, email, verify_code):
                    print(f"[-] {email} 验证码无效")
                    continue
                
                # Step 4: 注册重试循环
                for attempt in range(3):
                    task_id = turnstile_service.create_task(site_url, config["site_key"])
                    # 这里不再打印获取 Token 的过程，只在失败时报错
                    token = turnstile_service.get_response(task_id)
                    
                    if not token or token == "CAPTCHA_FAIL":
                        print(f"[-] {email} CAPTCHA 失败，重试...")
                        continue

                    headers = {
                        "user-agent": user_agent, "accept": "text/x-component", "content-type": "text/plain;charset=UTF-8",
                        "origin": site_url, "referer": f"{site_url}/sign-up", "cookie": f"__cf_bm={session.cookies.get('__cf_bm','')}",
                        "next-router-state-tree": config["state_tree"],
                    }
                    if final_action_id:
                        headers["next-action"] = final_action_id
                    payload = [{
                        "emailValidationCode": verify_code,
                        "createUserAndSessionRequest": {
                            "email": email, "givenName": generate_random_name(), "familyName": generate_random_name(),
                            "clearTextPassword": password, "tosAcceptedVersion": "$undefined"
                        },
                        "turnstileToken": token, "promptOnDuplicateEmail": True
                    }]
                    
                    with post_lock:
                        res = session.post(f"{site_url}/sign-up", json=payload, headers=headers)
                    
                    if res.status_code == 200:
                        match = re.search(r'(https://[^" \s]+set-cookie\?q=[^:" \s]+)1:', res.text)
                        if match:
                            verify_url = match.group(1)
                            session.get(verify_url, allow_redirects=True)
                            sso = session.cookies.get("sso")
                            if sso:
                                with file_lock:
                                    task_keys_dir = keys_dir()
                                    task_keys_dir.mkdir(parents=True, exist_ok=True)
                                    with open(task_keys_dir / "grok.txt", "a", encoding="utf-8") as f:
                                        f.write(sso + "\n")
                                    with open(task_keys_dir / "accounts.txt", "a", encoding="utf-8") as f:
                                        f.write(f"{email}:{password}:{sso}\n")
                                    global success_count
                                    success_count += 1
                                    avg = (time.time() - start_time) / success_count
                                    print(f"[✓] 注册成功: {email} | SSO: {sso[:15]}... | 平均: {avg:.1f}s")
                                break  # 跳出 for 循环，继续 while True 注册下一个
                    
                    print(f"[-] {email} 提交失败 ({res.status_code})")
                    time.sleep(3) # 失败稍微等一下
                else:
                    # 如果重试 3 次都失败 (for 循环没有被 break)
                    print(f"[-] {email} 放弃，换号")
                    time.sleep(5)

        except Exception as e:
            # 捕获所有异常防止线程退出
            print(f"[-] 异常: {str(e)[:50]}")
            time.sleep(5)

def main():
    print("=" * 60 + "\nGrok 注册机\n" + "=" * 60)
    
    # 1. 扫描参数
    print("[*] 正在初始化...")
    start_url = f"{site_url}/sign-up"
    with requests.Session(impersonate="chrome120") as s:
        try:
            html = s.get(start_url).text
            # Key
            key_match = re.search(r'sitekey":"(0x4[a-zA-Z0-9_-]+)"', html)
            if key_match: config["site_key"] = key_match.group(1)
            # Tree
            tree_match = re.search(r'next-router-state-tree":"([^"]+)"', html)
            if tree_match: config["state_tree"] = tree_match.group(1)
            # Action ID
            # 直接用正则从 HTML 抓取所有 /_next/static/chunks/*.js
            js_urls = [urljoin(start_url, m.group(0)) for m in re.finditer(r"/_next/static/chunks/[^\"'\s>]+\.js", html)]
            if not js_urls:
                html_preview = html[:500].replace("\n", " ")
                print(f"[Warn] HTML 长度 {len(html)}, 未解析出 JS，前500字符预览: {html_preview}")
            action_found = None
            for js_url in js_urls:
                try:
                    js_content = s.get(js_url, timeout=15).text
                except Exception as e:
                    continue
                match = re.search(r'7f[a-fA-F0-9]{40}', js_content)
                if match:
                    action_found = match.group(0)
                    print(f"[+] Action ID: {action_found}")
                    break
            if action_found:
                config["action_id"] = action_found
        except Exception as e:
            print(f"[-] 初始化扫描失败: {e}")
            return

    if not config["action_id"]:
        print("[-] 错误: 未找到 Action ID")
        return

    # 2. 启动
    try:
        t = int(input("\n并发数 (默认8): ").strip() or 8)
    except: t = 8
    
    print(f"[*] 启动 {t} 个线程...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=t) as executor:
        # 只提交与线程数相等的任务，让它们在内部无限循环
        futures = [executor.submit(register_single_thread) for _ in range(t)]
        try:
            concurrent.futures.wait(futures)
        except KeyboardInterrupt:
            print("\n[!] 收到中断信号，准备退出...")

if __name__ == "__main__":
    main()
