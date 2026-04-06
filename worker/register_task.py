import argparse
import json
import sys
import traceback

from lib.chatgpt_client import ChatGPTClient
from lib.oauth_client import OAuthClient
from lib.outlook_mail_client import OutlookMailClient
from lib.token_manager import TokenManager
from lib.utils import generate_random_birthday, generate_random_name, generate_random_password


def emit(event, **payload):
    print("__RESULT__ " + json.dumps({"event": event, **payload}, ensure_ascii=False), flush=True)


def register_one(index, total, config, mail_client, token_manager):
    account = None
    email = ""
    password = ""
    try:
        print(f"[{index}/{total}] 获取 Outlook 邮箱...", flush=True)
        email, account = mail_client.create_temp_email()
        email = str(email).strip().lower()
        print(f"[{index}/{total}] 邮箱: {email}", flush=True)

        password = generate_random_password()
        first_name, last_name = generate_random_name()
        birthdate = generate_random_birthday()
        chatgpt_client = ChatGPTClient(verbose=True)

        success, message = chatgpt_client.register_complete_flow(email, password, first_name, last_name, birthdate, mail_client)
        if not success:
            print(f"[{index}/{total}] 注册失败: {message}", flush=True)
            emit("account_failed", email=email, message=message)
            return False

        oauth_client = OAuthClient({"oauth_issuer": "https://auth.openai.com"}, verbose=True)
        tokens = oauth_client.login_and_get_tokens(
            email,
            password,
            chatgpt_client.device_id,
            chatgpt_client.ua,
            chatgpt_client.sec_ch_ua,
            chatgpt_client.impersonate,
            mail_client,
        )

        token_manager.save_account(email, password)
        if tokens:
            token_manager.save_tokens(email, tokens)

        mail_client.mark_registered(email, existing_tags=(account or {}).get("tag_keys"))
        print(f"[{index}/{total}] 注册成功并已打标签", flush=True)
        emit("account_success", email=email)
        return True
    except Exception as exc:
        print(f"[{index}/{total}] 异常: {exc}", flush=True)
        traceback.print_exc()
        emit("account_failed", email=email, message=str(exc))
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as handle:
        config = json.load(handle)

    credential = config["credential"]
    quantity = max(1, int(config.get("quantity") or 1))
    mail_client = OutlookMailClient(
        credential["base_url"],
        credential["api_key"],
        credential.get("category_key") or "mregister",
        credential.get("tag_key") or "chatgpt_registered",
    )
    token_manager = TokenManager(config["output_dir"])

    print("=" * 60, flush=True)
    print("MREGISTER worker started", flush=True)
    print(f"Task ID: {config.get('task_id')}", flush=True)
    print(f"Target quantity: {quantity}", flush=True)
    print(f"Category key: {credential.get('category_key')}", flush=True)
    print(f"Tag key: {credential.get('tag_key')}", flush=True)
    print("=" * 60, flush=True)

    success_count = 0
    for index in range(1, quantity + 1):
        if register_one(index, quantity, config, mail_client, token_manager):
            success_count += 1

    print(f"Worker finished, success={success_count}, total={quantity}", flush=True)
    return 0 if success_count >= quantity else 1


if __name__ == "__main__":
    sys.exit(main())
