"""
ChatGPT batch registration tool v2.0.
"""

import argparse
import sys
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

from lib.chatgpt_client import ChatGPTClient
from lib.config import as_bool, load_config
from lib.oauth_client import OAuthClient
from lib.skymail_client import init_mail_client
from lib.token_manager import TokenManager
from lib.utils import generate_random_birthday, generate_random_name, generate_random_password


warnings.filterwarnings("ignore", message="Unverified HTTPS request")


def register_one_account(idx, total, mail_client, token_manager, oauth_client, config, max_retries=3):
    """
    Register a single account with retries.

    Returns:
        tuple[bool, str, str, str]: (success, email, password, message)
    """
    tag = f"[{idx}/{total}]"

    for attempt in range(max_retries):
        if attempt > 0:
            print(f"\n{tag} 重试注册 (尝试 {attempt + 1}/{max_retries})...")
            time.sleep(1)
        else:
            print(f"\n{tag} 开始注册...")

        try:
            print(f"{tag} 创建临时邮箱...")
            email, _mail_token = mail_client.create_temp_email()
            print(f"{tag} 邮箱: {email}")

            password = generate_random_password()
            first_name, last_name = generate_random_name()
            birthdate = generate_random_birthday()

            print(f"{tag} 密码: {password}")
            print(f"{tag} 姓名: {first_name} {last_name}")

            proxy = config.get("proxy", "")
            chatgpt_client = ChatGPTClient(proxy=proxy, verbose=True)

            print(f"{tag} 开始注册流程...")
            success, msg = chatgpt_client.register_complete_flow(
                email, password, first_name, last_name, birthdate, mail_client
            )

            if not success:
                is_tls_error = "TLS" in msg or "SSL" in msg or "curl: (35)" in msg
                if is_tls_error and attempt < max_retries - 1:
                    print(f"{tag} ⚠️ TLS 错误，准备重试: {msg}")
                    continue
                print(f"{tag} ❌ 注册失败: {msg}")
                return False, email, password, msg

            print(f"{tag} ✅ 注册成功")

            enable_oauth = as_bool(config.get("enable_oauth", True))
            oauth_required = as_bool(config.get("oauth_required", True))

            if enable_oauth:
                print(f"{tag} 开始 OAuth 登录...")
                oauth_client_reuse = OAuthClient(config, proxy=config.get("proxy", ""), verbose=True)
                oauth_client_reuse.session = chatgpt_client.session

                tokens = oauth_client_reuse.login_and_get_tokens(
                    email,
                    password,
                    chatgpt_client.device_id,
                    chatgpt_client.ua,
                    chatgpt_client.sec_ch_ua,
                    chatgpt_client.impersonate,
                    mail_client,
                )

                if tokens and tokens.get("access_token"):
                    print(f"{tag} ✅ OAuth 成功")
                    token_manager.save_tokens(email, tokens)

                    output_file = config.get("output_file", "registered_accounts.txt")
                    with threading.Lock():
                        with open(output_file, "a", encoding="utf-8") as handle:
                            handle.write(f"{email}----{password}----oauth=ok\n")

                    return True, email, password, "注册成功 + OAuth 成功"

                print(f"{tag} ⚠️ OAuth 失败")
                if oauth_required:
                    if attempt < max_retries - 1:
                        print(f"{tag} OAuth 失败，准备重试整个流程...")
                        continue
                    return False, email, password, "OAuth 失败（必需）"

                output_file = config.get("output_file", "registered_accounts.txt")
                with threading.Lock():
                    with open(output_file, "a", encoding="utf-8") as handle:
                        handle.write(f"{email}----{password}----oauth=failed\n")
                return True, email, password, "注册成功（OAuth 失败）"

            output_file = config.get("output_file", "registered_accounts.txt")
            with threading.Lock():
                with open(output_file, "a", encoding="utf-8") as handle:
                    handle.write(f"{email}----{password}\n")
            return True, email, password, "注册成功"

        except Exception as exc:
            error_msg = str(exc)
            is_tls_error = "TLS" in error_msg or "SSL" in error_msg or "curl: (35)" in error_msg

            if is_tls_error and attempt < max_retries - 1:
                print(f"{tag} ⚠️ 异常 (TLS 错误)，准备重试: {error_msg[:100]}")
                continue

            print(f"{tag} ❌ 注册失败: {exc}")
            import traceback

            traceback.print_exc()
            return False, "", "", error_msg

    return False, "", "", "重试次数已用尽"


def main():
    """Run the CLI."""
    parser = argparse.ArgumentParser(description="ChatGPT 批量自动注册工具 v2.0")
    parser.add_argument("-n", "--num", type=int, default=1, help="注册账号数量（默认: 1）")
    parser.add_argument("-w", "--workers", type=int, default=1, help="并发线程数（默认: 1）")
    parser.add_argument("--no-oauth", action="store_true", help="禁用 OAuth 登录")
    args = parser.parse_args()

    config = load_config()
    if args.no_oauth:
        config["enable_oauth"] = False

    mail_provider = str(config.get("mail_provider", "skymail")).strip().lower().replace("-", "_") or "skymail"
    mail_provider_labels = {
        "gptmail": "GPTMail",
        "moemail": "MoeMail",
        "cloudflare_temp_email": "Cloudflare Temp Email",
        "skymail": "Skymail",
    }
    mail_provider_label = mail_provider_labels.get(mail_provider, mail_provider)

    print("=" * 60)
    print("  ChatGPT 批量自动注册工具 v2.0 (模块化版本)")
    print(f"  使用 {mail_provider_label} 邮件服务")
    print("=" * 60)

    total_accounts = args.num
    max_workers = args.workers

    mail_client = init_mail_client(config)
    token_manager = TokenManager(config)
    oauth_client = OAuthClient(config, proxy=config.get("proxy", ""), verbose=True)

    output_file = config.get("output_file", "registered_accounts.txt")
    enable_oauth = as_bool(config.get("enable_oauth", True))

    print("\n配置信息:")
    print(f"  注册数量: {total_accounts}")
    print(f"  并发数: {max_workers}")
    print(f"  输出文件: {output_file}")
    print(f"  邮件服务: {mail_provider}")
    print(f"  邮件 API: {mail_client.api_base}")
    print(f"  Token 目录: {token_manager.token_dir}")
    print(f"  启用 OAuth: {enable_oauth}")
    print()

    success_count = 0
    failed_count = 0
    start_time = time.time()

    if max_workers == 1:
        for i in range(1, total_accounts + 1):
            success, email, password, msg = register_one_account(
                i, total_accounts, mail_client, token_manager, oauth_client, config
            )
            if success:
                success_count += 1
            else:
                failed_count += 1
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    register_one_account,
                    i,
                    total_accounts,
                    mail_client,
                    token_manager,
                    oauth_client,
                    config,
                )
                for i in range(1, total_accounts + 1)
            ]

            for future in as_completed(futures):
                try:
                    success, email, password, msg = future.result()
                    if success:
                        success_count += 1
                    else:
                        failed_count += 1
                except Exception as exc:
                    print(f"❌ 任务异常: {exc}")
                    failed_count += 1

    total_time = time.time() - start_time

    print("\n" + "=" * 60)
    print("注册完成！")
    print(f"  成功: {success_count}")
    print(f"  失败: {failed_count}")
    print(f"  总计: {total_accounts}")
    print(f"  总耗时: {total_time:.1f}s")
    if total_accounts > 0:
        print(f"  平均耗时: {total_time / total_accounts:.1f}s/账号")
    print("=" * 60)

    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n用户中断")
        sys.exit(0)
    except Exception as exc:
        print(f"\n\n程序异常: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
