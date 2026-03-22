from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import zipfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from chatgpt_register_v2.lib.proxy_utils import normalize_proxy_url


ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = WEB_DIR / "runtime"
TASKS_DIR = RUNTIME_DIR / "tasks"
DB_PATH = RUNTIME_DIR / "app.db"
SESSION_COOKIE = "register_console_session"
SESSION_TTL_HOURS = max(1, int(os.getenv("WEB_CONSOLE_SESSION_TTL_HOURS", "24")))
MAX_CONCURRENT_TASKS = max(1, int(os.getenv("WEB_CONSOLE_MAX_CONCURRENT_TASKS", "2")))
POLL_INTERVAL_SECONDS = max(1.0, float(os.getenv("WEB_CONSOLE_POLL_INTERVAL", "2.0")))

PLATFORMS = {
    "chatgpt-register-v2": {
        "label": "ChatGPT Register v2",
        "requires_email_credential": True,
        "requires_captcha_credential": False,
        "supports_proxy": True,
        "default_concurrency": 1,
        "notes": "Uses the configured mail provider via the chatgpt_register_v2 mail adapter and writes account/token files into the task directory.",
    },
    "grok-register": {
        "label": "Grok Register",
        "requires_email_credential": False,
        "requires_captcha_credential": True,
        "supports_proxy": False,
        "default_concurrency": 4,
        "notes": "Uses YesCaptcha. The worker feeds the original CLI with a concurrency value via stdin.",
    },
}

EMAIL_CREDENTIAL_KINDS = {"gptmail", "moemail", "cloudflare_temp_email"}
SUPPORTED_CREDENTIAL_KINDS = EMAIL_CREDENTIAL_KINDS | {"yescaptcha"}

UI_TRANSLATIONS = {
    "zh-CN": {
        "site_title": "MREGISTER",
        "request_failed": "请求失败",
        "brand_console": "Register Console",
        "brand_name": "MREGISTER",
        "topbar_workspace": "工作区",
        "auth_setup_title": "首次打开先设置管理员密码",
        "auth_setup_desc": "密码会保存为本地哈希值。未设置密码前，任务、凭据、代理和 API 都不会开放。",
        "auth_login_title": "输入管理员密码进入控制台",
        "auth_login_desc": "当前站点已经启用密码保护，登录后才可查看任务、下载压缩包和操作 API Key。",
        "auth_password": "管理员密码",
        "auth_setup_submit": "保存并进入后台",
        "auth_login_submit": "登录",
        "nav_dashboard": "首页",
        "nav_credentials": "凭据",
        "nav_proxies": "代理",
        "nav_create_task": "新建任务",
        "nav_task_detail": "任务详情",
        "nav_schedules": "定时任务",
        "nav_api_keys": "API 接口",
        "nav_docs": "API文档",
        "nav_logout": "退出登录",
        "toggle_sidebar": "收起或展开侧边栏",
        "open_sidebar": "打开侧边栏",
        "close_sidebar": "关闭侧边栏",
        "section_overview": "总览与默认配置",
        "panel_defaults_title": "默认设置",
        "panel_defaults_desc": "API 创建任务时会优先使用这里的默认邮件凭据、默认验证码凭据和默认代理。",
        "default_gptmail": "默认邮件凭据",
        "default_yescaptcha": "默认 YesCaptcha",
        "default_proxy": "默认代理",
        "save_defaults": "保存默认设置",
        "panel_recent_tasks_title": "最近任务",
        "panel_recent_tasks_desc": "点任意任务可直接跳到详情页查看控制台输出。",
        "section_credentials": "凭据管理",
        "credentials_create_title": "新增凭据",
        "credentials_create_desc": "支持 GPTMail、MoeMail、Cloudflare Temp Email 与 YesCaptcha，保存后可直接设为默认。",
        "gptmail_optional_hint": "GPTMail 的 Base URL、邮箱前缀、邮箱域名都有默认值，可直接留空不填写。",
        "moemail_optional_hint": "MoeMail 需要站点 Base URL 和 API Key，邮箱前缀与域名可按需填写。",
        "cloudflare_optional_hint": "Cloudflare Temp Email 需要 Worker Base URL 和管理员访问密码；如果站点启用了全局访问密码，也可以一并填写。",
        "credentials_saved_title": "已保存凭据",
        "credentials_saved_desc": "支持删除、查看备注、设为默认。",
        "field_name": "名称",
        "field_kind": "类型",
        "field_api_key": "API Key",
        "field_secret": "辅助密钥",
        "field_base_url": "Base URL",
        "field_prefix": "邮箱前缀",
        "field_domain": "邮箱域名",
        "field_secret_placeholder": "按当前凭据类型填写辅助密钥",
        "field_base_url_placeholder": "留空使用默认 Base URL",
        "field_prefix_placeholder": "留空使用默认邮箱前缀",
        "field_domain_placeholder": "留空使用默认邮箱域名",
        "field_notes": "备注",
        "save_credential": "保存凭据",
        "credential_kind_gptmail": "GPTMail",
        "credential_kind_moemail": "MoeMail",
        "credential_kind_cloudflare_temp_email": "Cloudflare Temp Email",
        "credential_kind_yescaptcha": "YesCaptcha",
        "credential_api_key_label_gptmail": "GPTMail API Key",
        "credential_api_key_label_moemail": "MoeMail API Key",
        "credential_api_key_label_cloudflare_temp_email": "管理员访问密码",
        "credential_api_key_label_yescaptcha": "YesCaptcha API Key",
        "credential_secret_label_cloudflare_temp_email": "站点访问密码",
        "credential_secret_placeholder_cloudflare_temp_email": "如果部署启用了 x-custom-auth，可在这里填写",
        "section_proxies": "代理管理",
        "proxies_create_title": "新增代理",
        "proxies_create_desc": "支持保存多个代理，并可指定为站点默认代理。",
        "proxies_saved_title": "已保存代理",
        "proxies_saved_desc": "任务可选择默认代理、指定代理或不使用代理。",
        "field_proxy_url": "代理地址",
        "save_proxy": "保存代理",
        "section_tasks": "新建任务",
        "field_task_name": "任务名称",
        "field_platform": "驱动",
        "field_quantity": "目标数量",
        "field_concurrency": "并发数",
        "field_email_credential": "邮件凭据",
        "field_captcha_credential": "验证码凭据",
        "field_proxy_mode": "代理模式",
        "field_proxy_select": "指定代理",
        "proxy_mode_none": "不使用代理",
        "proxy_mode_default": "使用默认代理",
        "proxy_mode_custom": "指定代理",
        "save_task": "创建并加入队列",
        "section_task_detail": "任务详情",
        "task_detail_note": "关闭网页不会停止任务，控制台输出会保存到任务目录，重新打开时会继续显示。",
        "task_list_title": "任务列表",
        "task_list_desc": "左侧筛选后只显示对应状态的任务。",
        "task_filter_status": "状态筛选",
        "task_filter_all": "全部状态",
        "console_title": "实时控制台",
        "section_schedules": "定时任务",
        "schedules_create_title": "新增定时任务",
        "schedules_create_desc": "每天在固定时间自动创建一个独立任务。",
        "schedules_saved_title": "已保存定时任务",
        "schedules_saved_desc": "可以启用、停用或删除。",
        "field_time_of_day": "执行时间",
        "field_use_default_proxy": "使用默认代理",
        "save_schedule": "保存定时任务",
        "cpamc_title": "配置 CPAMC",
        "cpamc_desc": "用于绑定 CLI Proxy API Management Center，仅处理 Codex / Grok 相关 JSON 导入。",
        "field_cpamc_enabled": "启用 CLI Proxy API Management Center",
        "field_cpamc_base_url": "域名/IP 链接",
        "field_cpamc_base_url_placeholder": "例如 http://127.0.0.1:8317 或 http://127.0.0.1:8317/v0/management",
        "field_cpamc_management_key": "管理密钥",
        "field_cpamc_management_key_placeholder": "输入 CPAMC Management Key",
        "save_cpamc": "保存 CPAMC 配置",
        "test_cpamc": "测试链接",
        "cpamc_status_linked": "已连接",
        "cpamc_status_unlinked": "未链接",
        "cpamc_status_disabled": "未启用",
        "cpamc_last_error": "最近错误：{value}",
        "cpamc_import_button": "导入到 CPAMC",
        "cpamc_import_disabled": "当前任务没有可导入的 JSON 文件",
        "cpamc_import_success": "已导入 {count} 个 JSON 文件到 CPAMC。",
        "cpamc_import_partial": "已导入 {success} 个，失败 {failed} 个。",
        "cpamc_import_result_title": "导入完成",
        "modal_close": "关闭",
        "section_api": "API 接口",
        "api_create_title": "创建 API Key",
        "api_create_desc": "新建成功后只会显示一次，请立即保存。",
        "api_saved_title": "已有 API Key",
        "api_saved_desc": "可用于外部程序调用创建任务、查询状态和下载结果。",
        "save_api_key": "生成 API Key",
        "section_docs": "API文档",
        "docs_intro_title": "总览",
        "docs_intro_desc": "控制台支持网页操作和外部 API 调用。外部 API 默认使用站点中已配置的默认邮件凭据、默认 YesCaptcha 和默认代理。通过 API 创建的任务会在完成 24 小时后自动清理。",
        "docs_deploy_title": "部署方式",
        "docs_deploy_desc": "推荐优先使用 Docker Compose 部署，默认直接拉取 `maishanhub/mregister:main` 镜像，便于快速上线和保留运行数据；如果只是本地调试，也可以直接用 Python 启动。",
        "docs_local_deploy_title": "本地 Python 启动",
        "docs_compose_deploy_title": "Docker Compose 启动",
        "docs_api_flow_title": "API 调用流程",
        "docs_api_flow_desc": "推荐顺序：先在控制台创建 API Key，再调用创建任务接口，随后轮询查询状态，最后在任务完成后下载压缩包。",
        "docs_endpoints_title": "接口列表",
        "docs_create_params_title": "创建任务参数",
        "docs_create_example_title": "创建任务示例",
        "docs_query_example_title": "查询任务示例",
        "docs_download_example_title": "下载结果示例",
        "docs_response_title": "返回说明",
        "docs_response_desc": "`completed_count` 表示任务当前真实完成数，不按尝试次数计算。只有任务完成并且压缩包生成后，查询接口才会返回 `download_url`。API 创建的任务会在 `auto_delete_at` 指定时间后自动删除。",
        "table_method": "方法",
        "table_path": "路径",
        "table_desc": "说明",
        "table_field": "字段",
        "table_type": "类型",
        "table_required": "必填",
        "endpoint_create_desc": "创建一个新的外部任务",
        "endpoint_query_desc": "查询任务状态、真实完成数量和下载地址",
        "endpoint_download_desc": "下载任务结果压缩包",
        "required_yes": "是",
        "required_no": "否",
        "param_platform_desc": "驱动名称，目前支持 `chatgpt-register-v2` 和 `grok-register`",
        "param_quantity_desc": "目标成功数量，系统按真实成功数判断完成，不按尝试次数计算",
        "param_use_proxy_desc": "是否启用默认代理，不传或传 false 表示不使用代理",
        "param_concurrency_desc": "并发数，默认 1",
        "param_name_desc": "自定义任务名，不传则由系统自动生成",
        "docs_flow_1": "1. 在“API 接口”页面创建 API Key。",
        "docs_flow_2": "2. 调用 `POST /api/external/tasks` 创建任务。",
        "docs_flow_3": "3. 轮询 `GET /api/external/tasks/{task_id}` 查询状态和完成数。",
        "docs_flow_4": "4. 任务完成后调用 `GET /api/external/tasks/{task_id}/download` 下载压缩包。",
        "dashboard_running_tasks": "运行中任务",
        "dashboard_completed_tasks": "已完成任务",
        "dashboard_credential_count": "凭据数量",
        "dashboard_proxy_count": "代理数量",
        "empty_tasks": "暂无任务",
        "empty_credentials": "暂无凭据",
        "empty_proxies": "暂无代理",
        "empty_filtered_tasks": "当前筛选下没有任务",
        "empty_schedules": "暂无定时任务",
        "empty_api_keys": "暂无 API Key",
        "default_badge": "默认",
        "created_at": "创建于 {value}",
        "last_used_at": "最近使用时间 {value}",
        "unused": "暂未使用",
        "use_default_gptmail": "使用默认邮件凭据",
        "use_default_yescaptcha": "使用默认 YesCaptcha",
        "choose_proxy": "选择一个代理",
        "no_default_gptmail": "不设置默认邮件凭据",
        "no_default_yescaptcha": "不设置默认 YesCaptcha",
        "no_default_proxy": "不使用默认代理",
        "current_default": "当前默认",
        "set_default": "设为默认",
        "delete": "删除",
        "enable": "启用",
        "disable": "停用",
        "stop_task": "停止任务",
        "download_zip": "下载压缩包",
        "delete_task": "删除任务",
        "save_now": "新建成功，请立即保存",
        "created_task_modal_title": "任务已创建",
        "created_task_modal_confirm": "前往任务详情",
        "created_task_modal_cancel": "继续创建任务",
        "status_queued": "排队中",
        "status_running": "运行中",
        "status_stopping": "停止中",
        "status_completed": "已完成",
        "status_partial": "部分完成",
        "status_failed": "失败",
        "status_stopped": "已停止",
        "status_interrupted": "已中断",
        "task_detail_empty_title": "当前筛选下没有任务",
        "task_detail_empty_desc": "调整左侧状态筛选，或先创建新的任务。",
        "console_wait": "等待选择任务后显示实时控制台输出。",
        "console_empty": "当前还没有控制台输出。",
        "task_header_meta": "{platform} | 目标数量 {quantity} | 完成数量 {completed} | 当前状态 {status}",
        "created_task_confirm": "任务 #{id} 已创建。可前往任务详情查看进度，或留在当前页面继续创建。",
        "delete_task_confirm": "删除任务 #{id}？",
        "delete_credential_confirm": "删除凭据 {name}？",
        "delete_proxy_confirm": "删除代理 {name}？",
        "delete_schedule_confirm": "删除这个定时任务？",
        "delete_api_key_confirm": "删除这个 API Key？",
        "schedule_meta": "{platform} | 每日 {time} | 数量 {quantity} | {enabled}",
        "schedule_proxy_on": "使用默认代理",
        "schedule_proxy_off": "不使用代理",
        "api_key_meta": "{prefix}... | 创建于 {created_at}",
    },
    "en": {
        "site_title": "MREGISTER",
        "request_failed": "Request failed",
        "brand_console": "Register Console",
        "brand_name": "MREGISTER",
        "topbar_workspace": "Workspace",
        "auth_setup_title": "Set the admin password on first visit",
        "auth_setup_desc": "The password is stored as a local hash. Tasks, credentials, proxies, and API access stay locked until it is configured.",
        "auth_login_title": "Enter the admin password",
        "auth_login_desc": "This site is password protected. Sign in before viewing tasks, downloading archives, or managing API keys.",
        "auth_password": "Admin password",
        "auth_setup_submit": "Save and enter console",
        "auth_login_submit": "Sign in",
        "nav_dashboard": "Dashboard",
        "nav_credentials": "Credentials",
        "nav_proxies": "Proxies",
        "nav_create_task": "New Task",
        "nav_task_detail": "Task Detail",
        "nav_schedules": "Schedules",
        "nav_api_keys": "API",
        "nav_docs": "API Docs",
        "nav_logout": "Sign out",
        "toggle_sidebar": "Collapse or expand sidebar",
        "open_sidebar": "Open sidebar",
        "close_sidebar": "Close sidebar",
        "section_overview": "Overview and Defaults",
        "panel_defaults_title": "Default settings",
        "panel_defaults_desc": "API-created tasks will use these default email credentials, captcha credentials, and proxy settings first.",
        "default_gptmail": "Default email credential",
        "default_yescaptcha": "Default YesCaptcha",
        "default_proxy": "Default proxy",
        "save_defaults": "Save defaults",
        "panel_recent_tasks_title": "Recent tasks",
        "panel_recent_tasks_desc": "Click any task to jump straight into the detail view and console output.",
        "section_credentials": "Credential Management",
        "credentials_create_title": "Add credential",
        "credentials_create_desc": "Supports GPTMail, MoeMail, Cloudflare Temp Email, and YesCaptcha. You can set the saved item as default immediately.",
        "gptmail_optional_hint": "For GPTMail, Base URL, email prefix, and email domain all have defaults, so you can leave them blank.",
        "moemail_optional_hint": "MoeMail requires a site Base URL and API Key. Prefix and domain are optional.",
        "cloudflare_optional_hint": "Cloudflare Temp Email requires the Worker Base URL and admin password. If the site also uses a global access password, fill it in as well.",
        "credentials_saved_title": "Saved credentials",
        "credentials_saved_desc": "Delete, review notes, and set defaults here.",
        "field_name": "Name",
        "field_kind": "Type",
        "field_api_key": "API Key",
        "field_secret": "Secondary secret",
        "field_base_url": "Base URL",
        "field_prefix": "Email prefix",
        "field_domain": "Email domain",
        "field_secret_placeholder": "Optional secondary secret for this credential type",
        "field_base_url_placeholder": "Leave blank to use the default Base URL",
        "field_prefix_placeholder": "Leave blank to use the default email prefix",
        "field_domain_placeholder": "Leave blank to use the default email domain",
        "field_notes": "Notes",
        "save_credential": "Save credential",
        "credential_kind_gptmail": "GPTMail",
        "credential_kind_moemail": "MoeMail",
        "credential_kind_cloudflare_temp_email": "Cloudflare Temp Email",
        "credential_kind_yescaptcha": "YesCaptcha",
        "credential_api_key_label_gptmail": "GPTMail API Key",
        "credential_api_key_label_moemail": "MoeMail API Key",
        "credential_api_key_label_cloudflare_temp_email": "Admin password",
        "credential_api_key_label_yescaptcha": "YesCaptcha API Key",
        "credential_secret_label_cloudflare_temp_email": "Site access password",
        "credential_secret_placeholder_cloudflare_temp_email": "Fill this if the deployment requires x-custom-auth",
        "section_proxies": "Proxy Management",
        "proxies_create_title": "Add proxy",
        "proxies_create_desc": "Save multiple proxies and promote one as the site-wide default.",
        "proxies_saved_title": "Saved proxies",
        "proxies_saved_desc": "Tasks can use the default proxy, a specific proxy, or no proxy at all.",
        "field_proxy_url": "Proxy URL",
        "save_proxy": "Save proxy",
        "section_tasks": "Create Task",
        "field_task_name": "Task name",
        "field_platform": "Driver",
        "field_quantity": "Target quantity",
        "field_concurrency": "Concurrency",
        "field_email_credential": "Email credential",
        "field_captcha_credential": "Captcha credential",
        "field_proxy_mode": "Proxy mode",
        "field_proxy_select": "Specific proxy",
        "proxy_mode_none": "No proxy",
        "proxy_mode_default": "Use default proxy",
        "proxy_mode_custom": "Use selected proxy",
        "save_task": "Create and queue task",
        "section_task_detail": "Task Detail",
        "task_detail_note": "Closing the page does not stop a task. Console output is saved in the task directory and will be shown again when you reopen it.",
        "task_list_title": "Task list",
        "task_list_desc": "The left list only shows tasks that match the selected status filter.",
        "task_filter_status": "Status filter",
        "task_filter_all": "All statuses",
        "console_title": "Live console",
        "section_schedules": "Schedules",
        "schedules_create_title": "Add schedule",
        "schedules_create_desc": "Create an independent task automatically at the same time every day.",
        "schedules_saved_title": "Saved schedules",
        "schedules_saved_desc": "Enable, disable, or delete scheduled tasks here.",
        "field_time_of_day": "Run time",
        "field_use_default_proxy": "Use default proxy",
        "save_schedule": "Save schedule",
        "cpamc_title": "Configure CPAMC",
        "cpamc_desc": "Bind CLI Proxy API Management Center here. This is only used for Codex / Grok related JSON imports.",
        "field_cpamc_enabled": "Enable CLI Proxy API Management Center",
        "field_cpamc_base_url": "Domain/IP link",
        "field_cpamc_base_url_placeholder": "For example http://127.0.0.1:8317 or http://127.0.0.1:8317/v0/management",
        "field_cpamc_management_key": "Management key",
        "field_cpamc_management_key_placeholder": "Enter the CPAMC management key",
        "save_cpamc": "Save CPAMC settings",
        "test_cpamc": "Test link",
        "cpamc_status_linked": "Connected",
        "cpamc_status_unlinked": "Not linked",
        "cpamc_status_disabled": "Disabled",
        "cpamc_last_error": "Last error: {value}",
        "cpamc_import_button": "Import to CPAMC",
        "cpamc_import_disabled": "This task has no importable JSON files",
        "cpamc_import_success": "Imported {count} JSON file(s) to CPAMC.",
        "cpamc_import_partial": "Imported {success}, failed {failed}.",
        "cpamc_import_result_title": "Import complete",
        "modal_close": "Close",
        "section_api": "API 接口",
        "api_create_title": "Create API key",
        "api_create_desc": "A new key is only shown once. Save it immediately.",
        "api_saved_title": "Existing API keys",
        "api_saved_desc": "Use these keys from external services to create tasks, query status, and download results.",
        "save_api_key": "Generate API key",
        "section_docs": "API Docs",
        "docs_intro_title": "总览",
        "docs_intro_desc": "The console supports both web operations and external API calls. External API tasks use the configured default email credential, default YesCaptcha credential, and default proxy first. API-created tasks are auto-cleaned 24 hours after completion.",
        "docs_deploy_title": "部署方式",
        "docs_deploy_desc": "推荐优先使用 Docker Compose 部署，默认直接拉取 `maishanhub/mregister:main` 镜像，便于快速上线和保留运行数据；如果只是本地调试，也可以直接用 Python 启动。",
        "docs_local_deploy_title": "本地 Python 启动",
        "docs_compose_deploy_title": "Docker Compose 启动",
        "docs_api_flow_title": "API 调用流程",
        "docs_api_flow_desc": "推荐顺序：先在控制台创建 API Key，再调用创建任务接口，随后轮询查询状态，最后在任务完成后下载压缩包。",
        "docs_endpoints_title": "接口列表",
        "docs_create_params_title": "创建任务参数",
        "docs_create_example_title": "创建任务示例",
        "docs_query_example_title": "查询任务示例",
        "docs_download_example_title": "下载结果示例",
        "docs_response_title": "返回说明",
        "docs_response_desc": "`completed_count` 表示任务当前真实完成数，不按尝试次数计算。只有任务完成并且压缩包生成后，查询接口才会返回 `download_url`。API 创建的任务会在 `auto_delete_at` 指定时间后自动删除。",
        "table_method": "Method",
        "table_path": "Path",
        "table_desc": "Description",
        "table_field": "Field",
        "table_type": "Type",
        "table_required": "Required",
        "endpoint_create_desc": "创建一个新的外部任务",
        "endpoint_query_desc": "查询任务状态、真实完成数量和下载地址",
        "endpoint_download_desc": "下载任务结果压缩包",
        "required_yes": "Yes",
        "required_no": "No",
        "param_platform_desc": "Driver name. Supported values: `chatgpt-register-v2` and `grok-register`",
        "param_quantity_desc": "目标成功数量，系统按真实成功数判断完成，不按尝试次数计算",
        "param_use_proxy_desc": "是否启用默认代理，不传或传 false 表示不使用代理",
        "param_concurrency_desc": "并发数，默认 1",
        "param_name_desc": "自定义任务名，不传则由系统自动生成",
        "docs_flow_1": "1. 在“API 接口”页面创建 API Key。",
        "docs_flow_2": "2. 调用 `POST /api/external/tasks` 创建任务。",
        "docs_flow_3": "3. 轮询 `GET /api/external/tasks/{task_id}` 查询状态和完成数。",
        "docs_flow_4": "4. 任务完成后调用 `GET /api/external/tasks/{task_id}/download` 下载压缩包。",
        "dashboard_running_tasks": "Running tasks",
        "dashboard_completed_tasks": "Completed tasks",
        "dashboard_credential_count": "Credentials",
        "dashboard_proxy_count": "Proxies",
        "empty_tasks": "No tasks yet",
        "empty_credentials": "No credentials yet",
        "empty_proxies": "No proxies yet",
        "empty_filtered_tasks": "No tasks match the current filter",
        "empty_schedules": "No schedules yet",
        "empty_api_keys": "No API keys yet",
        "default_badge": "default",
        "created_at": "Created at {value}",
        "last_used_at": "Last used {value}",
        "unused": "Not used yet",
        "use_default_gptmail": "Use default email credential",
        "use_default_yescaptcha": "Use default YesCaptcha",
        "choose_proxy": "Choose a proxy",
        "no_default_gptmail": "No default email credential",
        "no_default_yescaptcha": "No default YesCaptcha",
        "no_default_proxy": "No default proxy",
        "current_default": "Current default",
        "set_default": "Set default",
        "delete": "Delete",
        "enable": "Enable",
        "disable": "Disable",
        "stop_task": "Stop task",
        "download_zip": "Download archive",
        "delete_task": "Delete task",
        "save_now": "Created successfully, save it now",
        "created_task_modal_title": "Task Created",
        "created_task_modal_confirm": "Open task detail",
        "created_task_modal_cancel": "Keep creating",
        "status_queued": "Queued",
        "status_running": "Running",
        "status_stopping": "Stopping",
        "status_completed": "Completed",
        "status_partial": "Partially completed",
        "status_failed": "Failed",
        "status_stopped": "Stopped",
        "status_interrupted": "Interrupted",
        "task_detail_empty_title": "No tasks match the current filter",
        "task_detail_empty_desc": "Adjust the status filter on the left, or create a new task first.",
        "console_wait": "Select a task to see live console output.",
        "console_empty": "No console output yet.",
        "task_header_meta": "{platform} | Target {quantity} | Completed {completed} | Status {status}",
        "created_task_confirm": "Task #{id} was created. Open task detail to check progress, or stay here and create another one.",
        "delete_task_confirm": "Delete task #{id}?",
        "delete_credential_confirm": "Delete credential {name}?",
        "delete_proxy_confirm": "Delete proxy {name}?",
        "delete_schedule_confirm": "Delete this schedule?",
        "delete_api_key_confirm": "Delete this API key?",
        "schedule_meta": "{platform} | Daily {time} | Quantity {quantity} | {enabled}",
        "schedule_proxy_on": "Use default proxy",
        "schedule_proxy_off": "No proxy",
        "api_key_meta": "{prefix}... | Created at {created_at}",
    },
}

DEFAULT_SETTING_KEYS = {
    "default_gptmail_credential_id": None,
    "default_yescaptcha_credential_id": None,
    "default_proxy_id": None,
}

CPAMC_SETTING_KEYS = {
    "cpamc_enabled": "0",
    "cpamc_base_url": "",
    "cpamc_management_key": "",
    "cpamc_linked": "0",
    "cpamc_last_error": "",
}

db_lock = threading.RLock()
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


def now() -> datetime:
    return datetime.now()


def now_iso() -> str:
    return now().strftime("%Y-%m-%d %H:%M:%S")


def date_iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def detect_ui_lang(request: Request) -> str:
    accept_language = (request.headers.get("accept-language") or "").lower()
    for raw_part in accept_language.split(","):
        token = raw_part.split(";")[0].strip()
        if token.startswith("zh"):
            return "zh-CN"
        if token.startswith("en"):
            return "en"
    return "zh-CN"


def get_ui_translations(lang: str) -> dict[str, str]:
    base = UI_TRANSLATIONS["zh-CN"]
    selected = UI_TRANSLATIONS.get(lang, {})
    return {**base, **selected}


def ensure_runtime_dirs() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    TASKS_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def init_db() -> None:
    ensure_runtime_dirs()
    with db_lock, get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL,
                api_key TEXT NOT NULL,
                secret TEXT,
                base_url TEXT,
                prefix TEXT,
                domain TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS proxies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                proxy_url TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                platform TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                email_credential_id INTEGER,
                captcha_credential_id INTEGER,
                concurrency INTEGER NOT NULL DEFAULT 1,
                proxy TEXT,
                task_dir TEXT NOT NULL,
                console_path TEXT NOT NULL,
                archive_path TEXT,
                requested_config_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                exit_code INTEGER,
                pid INTEGER,
                last_error TEXT,
                source TEXT NOT NULL DEFAULT 'ui',
                auto_delete_at TEXT,
                FOREIGN KEY(email_credential_id) REFERENCES credentials(id),
                FOREIGN KEY(captcha_credential_id) REFERENCES credentials(id)
            );

            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                platform TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                concurrency INTEGER NOT NULL DEFAULT 1,
                time_of_day TEXT NOT NULL,
                use_proxy INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                last_run_date TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                key_hash TEXT NOT NULL UNIQUE,
                key_prefix TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_used_at TEXT
            );
            """
        )
        ensure_columns(
            conn,
            "credentials",
            {
                "secret": "TEXT",
            },
        )
        ensure_columns(
            conn,
            "tasks",
            {
                "source": "TEXT NOT NULL DEFAULT 'ui'",
                "auto_delete_at": "TEXT",
            },
        )
        conn.commit()


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with db_lock, get_connection() as conn:
        return conn.execute(query, params).fetchall()


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    with db_lock, get_connection() as conn:
        return conn.execute(query, params).fetchone()


def execute(query: str, params: tuple[Any, ...] = ()) -> int:
    with db_lock, get_connection() as conn:
        cursor = conn.execute(query, params)
        conn.commit()
        return int(cursor.lastrowid or 0)


def execute_no_return(query: str, params: tuple[Any, ...] = ()) -> None:
    with db_lock, get_connection() as conn:
        conn.execute(query, params)
        conn.commit()


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_tail(path: Path, limit: int = 30000) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        fh.seek(max(0, size - limit))
        return fh.read().decode("utf-8", errors="replace")


def get_setting(key: str) -> str | None:
    row = fetch_one("SELECT value FROM settings WHERE key = ?", (key,))
    return None if row is None else str(row["value"])


def set_setting(key: str, value: str | None) -> None:
    if value is None:
        execute_no_return("DELETE FROM settings WHERE key = ?", (key,))
        return
    execute_no_return(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, value, now_iso()),
    )


def get_defaults() -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    for key in DEFAULT_SETTING_KEYS:
        raw = get_setting(key)
        result[key] = int(raw) if raw and raw.isdigit() else None
    return result


def normalize_cpamc_base_url(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = f"http://{raw}"
    parsed = urlsplit(raw)
    if not parsed.netloc:
        raise HTTPException(status_code=400, detail="CPAMC link is invalid")
    path = (parsed.path or "").rstrip("/")
    if not path:
        path = "/v0/management"
    elif not path.endswith("/v0/management"):
        path = f"{path}/v0/management"
    return urlunsplit((parsed.scheme or "http", parsed.netloc, path, "", ""))


def get_cpamc_settings() -> dict[str, Any]:
    enabled = get_setting("cpamc_enabled") == "1"
    base_url = (get_setting("cpamc_base_url") or "").strip()
    management_key = (get_setting("cpamc_management_key") or "").strip()
    linked = get_setting("cpamc_linked") == "1"
    last_error = (get_setting("cpamc_last_error") or "").strip()
    return {
        "enabled": enabled,
        "base_url": base_url,
        "management_key": management_key,
        "linked": linked,
        "last_error": last_error,
    }


def set_cpamc_settings(settings: dict[str, Any]) -> dict[str, Any]:
    set_setting("cpamc_enabled", "1" if settings.get("enabled") else "0")
    set_setting("cpamc_base_url", str(settings.get("base_url") or "").strip())
    set_setting("cpamc_management_key", str(settings.get("management_key") or "").strip())
    set_setting("cpamc_linked", "1" if settings.get("linked") else "0")
    set_setting("cpamc_last_error", str(settings.get("last_error") or "").strip())
    return get_cpamc_settings()


def cpamc_headers(management_key: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {management_key}",
        "X-Management-Key": management_key,
    }
    if extra:
        headers.update(extra)
    return headers


def cpamc_request(
    method: str,
    *,
    base_url: str,
    management_key: str,
    path: str,
    **kwargs: Any,
) -> requests.Response:
    target = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    headers = kwargs.pop("headers", {})
    return requests.request(
        method=method,
        url=target,
        headers=cpamc_headers(management_key, headers),
        timeout=20,
        **kwargs,
    )


def parse_cpamc_error(response: requests.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("message") or payload.get("error") or payload.get("detail")
        if detail:
            return str(detail)
    text = (response.text or "").strip()
    if text:
        return text[:240]
    return f"HTTP {response.status_code}"


def cpamc_import_candidates(task: sqlite3.Row | dict[str, Any], *, validate: bool) -> list[Path]:
    task_dir = Path(task["task_dir"])
    candidate_dirs = [
        task_dir / "output" / "tokens",
        task_dir / "keys",
    ]
    files: list[Path] = []
    for directory in candidate_dirs:
        if not directory.exists():
            continue
        for file_path in sorted(directory.glob("*.json")):
            if not validate:
                files.append(file_path)
                continue
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            token_type = str(payload.get("type") or "").strip().lower()
            if token_type in {"codex", "grok"} or ("access_token" in payload and "refresh_token" in payload):
                files.append(file_path)
    return files


def hash_password(password: str, salt_hex: str | None = None) -> str:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or "$" not in stored:
        return False
    salt_hex, expected = stored.split("$", 1)
    actual = hash_password(password, salt_hex).split("$", 1)[1]
    return hmac.compare_digest(actual, expected)


def auth_is_configured() -> bool:
    return bool(get_setting("admin_password_hash"))


def cleanup_expired_sessions() -> None:
    execute_no_return("DELETE FROM sessions WHERE expires_at <= ?", (now_iso(),))


def create_session_token() -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = date_iso(now() + timedelta(hours=SESSION_TTL_HOURS))
    execute_no_return(
        "INSERT INTO sessions (token_hash, created_at, expires_at) VALUES (?, ?, ?)",
        (token_hash, now_iso(), expires_at),
    )
    return raw_token, expires_at


def delete_session(raw_token: str | None) -> None:
    if not raw_token:
        return
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    execute_no_return("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


def is_authenticated_request(request: Request) -> bool:
    cleanup_expired_sessions()
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        return False
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    row = fetch_one("SELECT id FROM sessions WHERE token_hash = ? AND expires_at > ?", (token_hash, now_iso()))
    return row is not None


def require_authenticated(request: Request) -> None:
    if not auth_is_configured():
        raise HTTPException(status_code=403, detail="Admin password is not configured yet")
    if not is_authenticated_request(request):
        raise HTTPException(status_code=401, detail="Login required")


def generate_api_key_secret() -> tuple[str, str, str]:
    raw = f"rc_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    prefix = raw[:12]
    return raw, key_hash, prefix


def verify_api_key(raw_key: str) -> sqlite3.Row | None:
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    row = fetch_one("SELECT * FROM api_keys WHERE key_hash = ? AND is_active = 1", (key_hash,))
    if row is not None:
        execute_no_return("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (now_iso(), int(row["id"])))
    return row


def get_request_api_key(request: Request) -> str | None:
    bearer = request.headers.get("Authorization", "").strip()
    if bearer.lower().startswith("bearer "):
        return bearer[7:].strip()
    header_key = request.headers.get("X-API-Key", "").strip()
    if header_key:
        return header_key
    return request.query_params.get("api_key")


def require_api_key(request: Request) -> sqlite3.Row:
    raw_key = get_request_api_key(request)
    if not raw_key:
        raise HTTPException(status_code=401, detail="API key required")
    row = verify_api_key(raw_key)
    if row is None:
        raise HTTPException(status_code=401, detail="API key is invalid")
    return row


def is_email_credential_kind(kind: str) -> bool:
    return kind in EMAIL_CREDENTIAL_KINDS


def serialize_credential(row: sqlite3.Row, *, include_secrets: bool = False) -> dict[str, Any]:
    item = row_to_dict(row)
    if not include_secrets:
        item.pop("api_key", None)
        item.pop("secret", None)
    return item


def get_credentials(*, include_secrets: bool = False) -> list[dict[str, Any]]:
    return [serialize_credential(row, include_secrets=include_secrets) for row in fetch_all("SELECT * FROM credentials ORDER BY kind, name")]


def get_proxies() -> list[dict[str, Any]]:
    return [row_to_dict(row) for row in fetch_all("SELECT * FROM proxies ORDER BY name")]


def get_schedules() -> list[dict[str, Any]]:
    return [row_to_dict(row) for row in fetch_all("SELECT * FROM schedules ORDER BY id DESC")]


def get_api_keys() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in fetch_all("SELECT * FROM api_keys ORDER BY id DESC"):
        item = row_to_dict(row)
        item.pop("key_hash", None)
        items.append(item)
    return items


def get_credential(credential_id: int) -> sqlite3.Row:
    row = fetch_one("SELECT * FROM credentials WHERE id = ?", (credential_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Credential not found")
    return row


def get_proxy(proxy_id: int) -> sqlite3.Row:
    row = fetch_one("SELECT * FROM proxies WHERE id = ?", (proxy_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Proxy not found")
    return row


def get_schedule(schedule_id: int) -> sqlite3.Row:
    row = fetch_one("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return row


def get_task(task_id: int) -> sqlite3.Row:
    row = fetch_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return row


def resolve_required_credential(kind: str, credential_id: int | None) -> sqlite3.Row:
    defaults = get_defaults()
    selected_id = credential_id
    if selected_id is None:
        selected_id = defaults["default_gptmail_credential_id"] if kind == "email" else defaults["default_yescaptcha_credential_id"]
    if selected_id is None:
        raise HTTPException(status_code=400, detail=f"No default {kind} credential is configured")
    credential = get_credential(int(selected_id))
    if kind == "email":
        if not is_email_credential_kind(str(credential["kind"])):
            raise HTTPException(status_code=400, detail=f"Credential {selected_id} is not a supported email credential")
        return credential
    if credential["kind"] != kind:
        raise HTTPException(status_code=400, detail=f"Credential {selected_id} is not of type {kind}")
    return credential


def resolve_proxy_value(proxy_mode: str, proxy_id: int | None) -> str | None:
    mode = proxy_mode or "none"
    defaults = get_defaults()
    if mode == "none":
        return None
    if mode == "default":
        selected = defaults["default_proxy_id"]
        if selected is None:
            raise HTTPException(status_code=400, detail="No default proxy is configured")
        return normalize_proxy_url(get_proxy(int(selected))["proxy_url"])
    if mode == "custom":
        if proxy_id is None:
            raise HTTPException(status_code=400, detail="A proxy must be selected")
        return normalize_proxy_url(get_proxy(proxy_id)["proxy_url"])
    raise HTTPException(status_code=400, detail="Unsupported proxy mode")


def task_paths(task: sqlite3.Row | dict[str, Any]) -> dict[str, Path]:
    task_dir = Path(task["task_dir"])
    if task["platform"] == "openai-register":
        results_file = task_dir / "output" / "tokens" / "accounts.txt"
    elif task["platform"] == "chatgpt-register-v2":
        results_file = task_dir / "output" / "registered_accounts.txt"
    else:
        results_file = task_dir / "keys" / "accounts.txt"
    archive_path = Path(task["archive_path"]) if task["archive_path"] else task_dir / "task_result.zip"
    return {
        "task_dir": task_dir,
        "console_path": Path(task["console_path"]),
        "results_file": results_file,
        "archive_path": archive_path,
    }


def count_result_lines(task: sqlite3.Row | dict[str, Any]) -> int:
    results_file = task_paths(task)["results_file"]
    if not results_file.exists():
        return 0
    with results_file.open("r", encoding="utf-8", errors="ignore") as fh:
        return sum(1 for line in fh if line.strip())


def create_archive(task: sqlite3.Row | dict[str, Any]) -> Path:
    paths = task_paths(task)
    archive_path = paths["archive_path"]
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in paths["task_dir"].rglob("*"):
            if file_path.is_dir() or file_path == archive_path:
                continue
            zf.write(file_path, file_path.relative_to(paths["task_dir"]))
    execute_no_return("UPDATE tasks SET archive_path = ? WHERE id = ?", (str(archive_path), int(task["id"])))
    return archive_path


def serialize_task(row: sqlite3.Row) -> dict[str, Any]:
    item = row_to_dict(row)
    item["results_count"] = count_result_lines(row)
    item["console_tail"] = read_tail(Path(item["console_path"]))
    item["cpamc_importable_count"] = len(cpamc_import_candidates(row, validate=False))
    try:
        item["requested_config"] = json.loads(item["requested_config_json"])
    except Exception:
        item["requested_config"] = {}
    return item


def get_tasks() -> list[dict[str, Any]]:
    return [serialize_task(row) for row in fetch_all("SELECT * FROM tasks ORDER BY id DESC")]


def dashboard_summary() -> dict[str, Any]:
    tasks = get_tasks()
    credentials = get_credentials()
    proxies = get_proxies()
    schedules = get_schedules()
    return {
        "running_tasks": sum(1 for task in tasks if task["status"] in {"queued", "running", "stopping"}),
        "completed_tasks": sum(1 for task in tasks if task["status"] == "completed"),
        "credential_count": len(credentials),
        "proxy_count": len(proxies),
        "schedule_count": len(schedules),
        "recent_tasks": tasks[:5],
    }


class CredentialCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str
    api_key: str = Field(min_length=1)
    secret: str | None = None
    base_url: str | None = None
    prefix: str | None = None
    domain: str | None = None
    notes: str | None = None


class ProxyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    proxy_url: str = Field(min_length=1, max_length=300)
    notes: str | None = None


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    platform: str
    quantity: int = Field(ge=1, le=100000)
    concurrency: int = Field(default=1, ge=1, le=64)
    time_of_day: str = Field(pattern=r"^\d{2}:\d{2}$")
    use_proxy: bool = False
    enabled: bool = True


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    platform: str
    quantity: int = Field(ge=1, le=100000)
    email_credential_id: int | None = None
    captcha_credential_id: int | None = None
    concurrency: int = Field(default=1, ge=1, le=64)
    proxy_mode: str = "none"
    proxy_id: int | None = None


class ExternalTaskCreate(BaseModel):
    platform: str
    quantity: int = Field(ge=1, le=100000)
    use_proxy: bool = False
    concurrency: int | None = Field(default=None, ge=1, le=64)
    name: str | None = None


class PasswordPayload(BaseModel):
    password: str = Field(min_length=8, max_length=256)


class DefaultSettingsPayload(BaseModel):
    default_gptmail_credential_id: int | None = None
    default_yescaptcha_credential_id: int | None = None
    default_proxy_id: int | None = None


class CpamcSettingsPayload(BaseModel):
    enabled: bool = False
    base_url: str | None = None
    management_key: str | None = None


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@dataclass
class TaskResolvedConfig:
    platform: str
    quantity: int
    concurrency: int
    email_credential_id: int | None
    captcha_credential_id: int | None
    proxy_value: str | None
    proxy_mode: str
    source: str
    auto_delete_at: str | None
    requested_config: dict[str, Any]


def validate_platform(platform: str) -> dict[str, Any]:
    if platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail="Unsupported platform")
    return PLATFORMS[platform]


def resolve_task_configuration(
    *,
    name: str,
    platform: str,
    quantity: int,
    concurrency: int | None,
    email_credential_id: int | None,
    captcha_credential_id: int | None,
    proxy_mode: str,
    proxy_id: int | None,
    source: str,
    auto_delete_at: str | None,
) -> tuple[str, TaskResolvedConfig]:
    spec = validate_platform(platform)
    resolved_name = name.strip() or f"{platform}-{now().strftime('%Y%m%d-%H%M%S')}"
    resolved_concurrency = concurrency or int(spec["default_concurrency"])
    resolved_concurrency = max(1, resolved_concurrency)

    email_row = None
    captcha_row = None
    if spec["requires_email_credential"]:
        email_row = resolve_required_credential("email", email_credential_id)
    if spec["requires_captcha_credential"]:
        captcha_row = resolve_required_credential("yescaptcha", captcha_credential_id)

    proxy_value = None
    if spec["supports_proxy"]:
        proxy_value = resolve_proxy_value(proxy_mode, proxy_id)

    requested_config = {
        "name": resolved_name,
        "platform": platform,
        "quantity": quantity,
        "concurrency": resolved_concurrency,
        "source": source,
        "proxy_mode": proxy_mode,
        "proxy_id": proxy_id,
        "proxy_value": proxy_value,
        "email_credential_id": int(email_row["id"]) if email_row else None,
        "captcha_credential_id": int(captcha_row["id"]) if captcha_row else None,
        "auto_delete_at": auto_delete_at,
    }
    return resolved_name, TaskResolvedConfig(
        platform=platform,
        quantity=quantity,
        concurrency=resolved_concurrency,
        email_credential_id=int(email_row["id"]) if email_row else None,
        captcha_credential_id=int(captcha_row["id"]) if captcha_row else None,
        proxy_value=proxy_value,
        proxy_mode=proxy_mode,
        source=source,
        auto_delete_at=auto_delete_at,
        requested_config=requested_config,
    )


def insert_task(*, name: str, config: TaskResolvedConfig) -> int:
    timestamp = now_iso()
    placeholder_dir = TASKS_DIR / f"pending_{int(time.time() * 1000)}_{secrets.token_hex(3)}"
    placeholder_dir.mkdir(parents=True, exist_ok=True)
    console_path = placeholder_dir / "console.log"
    task_id = execute(
        """
        INSERT INTO tasks (
            name, platform, quantity, status, email_credential_id, captcha_credential_id, concurrency,
            proxy, task_dir, console_path, archive_path, requested_config_json, created_at, source, auto_delete_at
        )
        VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)
        """,
        (
            name,
            config.platform,
            config.quantity,
            config.email_credential_id,
            config.captcha_credential_id,
            config.concurrency,
            config.proxy_value,
            str(placeholder_dir),
            str(console_path),
            json.dumps(config.requested_config, ensure_ascii=False),
            timestamp,
            config.source,
            config.auto_delete_at,
        ),
    )
    final_dir = TASKS_DIR / f"task_{task_id}"
    final_console_path = final_dir / "console.log"
    if placeholder_dir.exists():
        if final_dir.exists():
            shutil.rmtree(final_dir, ignore_errors=True)
        placeholder_dir.rename(final_dir)
    execute_no_return(
        "UPDATE tasks SET task_dir = ?, console_path = ? WHERE id = ?",
        (str(final_dir), str(final_console_path), task_id),
    )
    write_json(final_dir / "task.json", {"id": task_id, **config.requested_config, "created_at": timestamp})
    return task_id


@dataclass
class ManagedProcess:
    task_id: int
    process: subprocess.Popen[str]
    log_handle: Any


class TaskSupervisor:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._processes: dict[int, ManagedProcess] = {}
        self._lock = threading.RLock()

    def start(self) -> None:
        self.recover_stale_tasks()
        self._thread = threading.Thread(target=self._run_loop, name="register-supervisor", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._stop_event.set()
        with self._lock:
            items = list(self._processes.values())
        for item in items:
            self._terminate_process(item.process)
            try:
                item.log_handle.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=5)

    def recover_stale_tasks(self) -> None:
        for row in fetch_all("SELECT * FROM tasks WHERE status IN ('running', 'stopping')"):
            execute_no_return(
                """
                UPDATE tasks
                SET status = 'interrupted',
                    finished_at = ?,
                    last_error = COALESCE(last_error, 'Process ended while the service was offline.'),
                    pid = NULL
                WHERE id = ?
                """,
                (now_iso(), int(row["id"])),
            )
            try:
                create_archive(get_task(int(row["id"])))
            except Exception:
                pass

    def stop_task(self, task_id: int) -> None:
        row = get_task(task_id)
        if row["status"] == "queued":
            execute_no_return(
                "UPDATE tasks SET status = 'stopped', finished_at = ?, last_error = ? WHERE id = ?",
                (now_iso(), "Task stopped before launch.", task_id),
            )
            create_archive(get_task(task_id))
            return
        with self._lock:
            managed = self._processes.get(task_id)
        if managed is None:
            raise HTTPException(status_code=409, detail="Task is not running")
        execute_no_return("UPDATE tasks SET status = 'stopping' WHERE id = ?", (task_id,))
        self._terminate_process(managed.process)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                cleanup_expired_sessions()
                self._finalize_finished()
                self._enforce_target_counts()
                self._trigger_schedules()
                self._cleanup_expired_tasks()
                self._launch_queued()
            except Exception as exc:
                print(f"[web-console] supervisor error: {exc}")
            time.sleep(POLL_INTERVAL_SECONDS)

    def _launch_queued(self) -> None:
        slots = MAX_CONCURRENT_TASKS - self._running_count()
        if slots <= 0:
            return
        queued = fetch_all("SELECT * FROM tasks WHERE status = 'queued' ORDER BY id ASC LIMIT ?", (slots,))
        for row in queued:
            self._start_task(row)

    def _running_count(self) -> int:
        with self._lock:
            return len(self._processes)

    def _start_task(self, task: sqlite3.Row) -> None:
        paths = task_paths(task)
        task_dir = paths["task_dir"]
        task_dir.mkdir(parents=True, exist_ok=True)
        console_path = paths["console_path"]
        requested = json.loads(task["requested_config_json"])

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        stdin_payload: str | None = None

        if task["platform"] == "openai-register":
            credential = get_credential(int(task["email_credential_id"]))
            env["GPTMAIL_API_KEY"] = credential["api_key"]
            if credential["base_url"]:
                env["GPTMAIL_BASE_URL"] = credential["base_url"]
            if credential["prefix"]:
                env["GPTMAIL_PREFIX"] = credential["prefix"]
            if credential["domain"]:
                env["GPTMAIL_DOMAIN"] = credential["domain"]
            command = [
                sys.executable,
                str(ROOT_DIR / "openai-register" / "openai_register.py"),
                "--output-dir",
                str(task_dir / "output"),
                "--sleep-min",
                "2",
                "--sleep-max",
                "5",
            ]
            if task["proxy"]:
                command.extend(["--proxy", str(task["proxy"])])
            cwd = ROOT_DIR / "openai-register"
        elif task["platform"] == "chatgpt-register-v2":
            credential = get_credential(int(task["email_credential_id"]))
            output_dir = task_dir / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            env["MAIL_PROVIDER"] = str(credential["kind"])
            env["MAIL_API_KEY"] = credential["api_key"]
            env["OUTPUT_FILE"] = str(output_dir / "registered_accounts.txt")
            env["AK_FILE"] = str(output_dir / "ak.txt")
            env["RK_FILE"] = str(output_dir / "rk.txt")
            env["TOKEN_JSON_DIR"] = str(output_dir / "tokens")
            if task["proxy"]:
                env["PROXY"] = str(task["proxy"])
            if credential["secret"]:
                env["MAIL_SECRET"] = credential["secret"]
            if credential["base_url"]:
                env["MAIL_BASE_URL"] = credential["base_url"]
            if credential["prefix"]:
                env["MAIL_PREFIX"] = credential["prefix"]
            if credential["domain"]:
                env["MAIL_DOMAIN"] = credential["domain"]
            command = [
                sys.executable,
                str(ROOT_DIR / "chatgpt_register_v2" / "chatgpt_register_v2.py"),
                "-n",
                str(int(task["quantity"])),
                "-w",
                str(int(task["concurrency"])),
            ]
            cwd = ROOT_DIR / "chatgpt_register_v2"
        elif task["platform"] == "grok-register":
            credential = get_credential(int(task["captcha_credential_id"]))
            env["YESCAPTCHA_KEY"] = credential["api_key"]
            command = [sys.executable, str(ROOT_DIR / "grok-register" / "grok.py")]
            cwd = task_dir
            stdin_payload = f"{int(task['concurrency'])}\n"
        else:
            raise RuntimeError(f"Unsupported platform: {task['platform']}")

        log_handle = console_path.open("a", encoding="utf-8", buffering=1)
        log_handle.write(f"[{now_iso()}] Starting task {task['id']} ({task['platform']})\n")
        log_handle.write(f"[{now_iso()}] Config: {json.dumps(requested, ensure_ascii=False)}\n")
        log_handle.flush()

        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.PIPE if stdin_payload is not None else None,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )
        if stdin_payload is not None and process.stdin is not None:
            process.stdin.write(stdin_payload)
            process.stdin.flush()
            process.stdin.close()

        execute_no_return(
            """
            UPDATE tasks
            SET status = 'running',
                started_at = ?,
                pid = ?,
                last_error = NULL
            WHERE id = ?
            """,
            (now_iso(), process.pid, int(task["id"])),
        )
        with self._lock:
            self._processes[int(task["id"])] = ManagedProcess(task_id=int(task["id"]), process=process, log_handle=log_handle)

    def _finalize_finished(self) -> None:
        with self._lock:
            items = list(self._processes.items())
        for task_id, item in items:
            exit_code = item.process.poll()
            if exit_code is None:
                continue
            try:
                item.log_handle.write(f"[{now_iso()}] Process exited with code {exit_code}\n")
                item.log_handle.flush()
            except Exception:
                pass
            try:
                item.log_handle.close()
            except Exception:
                pass
            with self._lock:
                self._processes.pop(task_id, None)
            self._complete_task(task_id, exit_code)

    def _enforce_target_counts(self) -> None:
        with self._lock:
            items = list(self._processes.items())
        for task_id, managed in items:
            row = fetch_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
            if row is None or row["status"] != "running":
                continue
            if count_result_lines(row) >= int(row["quantity"]):
                execute_no_return("UPDATE tasks SET status = 'stopping' WHERE id = ?", (task_id,))
                self._terminate_process(managed.process)

    def _trigger_schedules(self) -> None:
        current_hm = now().strftime("%H:%M")
        today = now().strftime("%Y-%m-%d")
        for schedule in fetch_all("SELECT * FROM schedules WHERE enabled = 1 ORDER BY id ASC"):
            if str(schedule["time_of_day"]) != current_hm:
                continue
            if schedule["last_run_date"] == today:
                continue
            try:
                quantity = int(schedule["quantity"])
                concurrency = int(schedule["concurrency"])
                proxy_mode = "default" if int(schedule["use_proxy"] or 0) else "none"
                schedule_name = f"{schedule['name']} {today}"
                _, config = resolve_task_configuration(
                    name=schedule_name,
                    platform=str(schedule["platform"]),
                    quantity=quantity,
                    concurrency=concurrency,
                    email_credential_id=None,
                    captcha_credential_id=None,
                    proxy_mode=proxy_mode,
                    proxy_id=None,
                    source="schedule",
                    auto_delete_at=None,
                )
                insert_task(name=schedule_name, config=config)
                execute_no_return(
                    "UPDATE schedules SET last_run_date = ?, updated_at = ? WHERE id = ?",
                    (today, now_iso(), int(schedule["id"])),
                )
            except Exception as exc:
                print(f"[web-console] schedule {schedule['id']} failed: {exc}")

    def _cleanup_expired_tasks(self) -> None:
        expired = fetch_all(
            """
            SELECT * FROM tasks
            WHERE auto_delete_at IS NOT NULL
              AND auto_delete_at <= ?
              AND status NOT IN ('queued', 'running', 'stopping')
            """,
            (now_iso(),),
        )
        for row in expired:
            paths = task_paths(row)
            try:
                shutil.rmtree(paths["task_dir"], ignore_errors=True)
            except Exception:
                pass
            if paths["archive_path"].exists():
                try:
                    paths["archive_path"].unlink()
                except Exception:
                    pass
            execute_no_return("DELETE FROM tasks WHERE id = ?", (int(row["id"]),))

    def _complete_task(self, task_id: int, exit_code: int) -> None:
        row = get_task(task_id)
        results_count = count_result_lines(row)
        quantity = int(row["quantity"])
        current_status = row["status"]
        exit_error = None if exit_code == 0 else f"Task exited with code {exit_code}."
        if results_count >= quantity:
            status = "completed"
            error = None
        elif current_status == "stopping":
            status = "stopped"
            error = row["last_error"] or "Task stopped by operator."
        elif results_count > 0:
            status = "partial"
            error = row["last_error"] or exit_error or f"Task finished with {results_count}/{quantity} successful results."
        else:
            status = "failed"
            error = row["last_error"] or exit_error or "Task finished without successful results."
        execute_no_return(
            """
            UPDATE tasks
            SET status = ?,
                finished_at = ?,
                exit_code = ?,
                pid = NULL,
                last_error = ?
            WHERE id = ?
            """,
            (status, now_iso(), exit_code, error, task_id),
        )
        create_archive(get_task(task_id))

    @staticmethod
    def _terminate_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=10)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass


supervisor = TaskSupervisor()


def state_payload() -> dict[str, Any]:
    return {
        "platforms": PLATFORMS,
        "defaults": get_defaults(),
        "cpamc": get_cpamc_settings(),
        "credentials": get_credentials(),
        "proxies": get_proxies(),
        "tasks": get_tasks(),
        "schedules": get_schedules(),
        "api_keys": get_api_keys(),
        "dashboard": dashboard_summary(),
        "max_concurrent_tasks": MAX_CONCURRENT_TASKS,
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    cleanup_expired_sessions()
    supervisor.start()
    yield
    supervisor.shutdown()


app = FastAPI(title="Register Task Console", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


def make_session_response(payload: dict[str, Any], raw_token: str | None = None, expires_at: str | None = None) -> JSONResponse:
    response = JSONResponse(payload)
    if raw_token and expires_at:
        response.set_cookie(
            SESSION_COOKIE,
            raw_token,
            httponly=True,
            samesite="lax",
            max_age=SESSION_TTL_HOURS * 3600,
            expires=expires_at,
        )
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    ui_lang = detect_ui_lang(request)
    translations = get_ui_translations(ui_lang)
    auth_view = "app"
    if not auth_is_configured():
        auth_view = "setup"
    elif not is_authenticated_request(request):
        auth_view = "login"
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "auth_view": auth_view,
            "platforms": PLATFORMS,
            "max_concurrent_tasks": MAX_CONCURRENT_TASKS,
            "api_base_url": str(request.base_url).rstrip("/"),
            "ui_lang": ui_lang,
            "t": translations,
            "translations_json": json.dumps(translations, ensure_ascii=False),
        },
    )


@app.get("/api/auth/state")
async def auth_state(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "configured": auth_is_configured(),
            "authenticated": is_authenticated_request(request) if auth_is_configured() else False,
        }
    )


@app.post("/api/auth/setup")
async def auth_setup(payload: PasswordPayload) -> JSONResponse:
    if auth_is_configured():
        raise HTTPException(status_code=409, detail="Admin password is already configured")
    set_setting("admin_password_hash", hash_password(payload.password))
    raw_token, expires_at = create_session_token()
    return make_session_response({"ok": True}, raw_token, expires_at)


@app.post("/api/auth/login")
async def auth_login(payload: PasswordPayload) -> JSONResponse:
    if not verify_password(payload.password, get_setting("admin_password_hash")):
        raise HTTPException(status_code=401, detail="Password is incorrect")
    raw_token, expires_at = create_session_token()
    return make_session_response({"ok": True}, raw_token, expires_at)


@app.post("/api/auth/logout")
async def auth_logout(request: Request) -> JSONResponse:
    delete_session(request.cookies.get(SESSION_COOKIE))
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/api/state")
async def api_state(request: Request) -> JSONResponse:
    require_authenticated(request)
    return JSONResponse(state_payload())


@app.post("/api/defaults")
async def update_defaults(payload: DefaultSettingsPayload, request: Request) -> JSONResponse:
    require_authenticated(request)
    if payload.default_gptmail_credential_id is not None and not is_email_credential_kind(str(get_credential(payload.default_gptmail_credential_id)["kind"])):
        raise HTTPException(status_code=400, detail="Default email credential is invalid")
    if payload.default_yescaptcha_credential_id is not None and get_credential(payload.default_yescaptcha_credential_id)["kind"] != "yescaptcha":
        raise HTTPException(status_code=400, detail="Default YesCaptcha credential is invalid")
    if payload.default_proxy_id is not None:
        get_proxy(payload.default_proxy_id)
    set_setting("default_gptmail_credential_id", str(payload.default_gptmail_credential_id) if payload.default_gptmail_credential_id else None)
    set_setting("default_yescaptcha_credential_id", str(payload.default_yescaptcha_credential_id) if payload.default_yescaptcha_credential_id else None)
    set_setting("default_proxy_id", str(payload.default_proxy_id) if payload.default_proxy_id else None)
    return JSONResponse({"ok": True, "defaults": get_defaults()})


@app.post("/api/cpamc")
async def update_cpamc_settings(payload: CpamcSettingsPayload, request: Request) -> JSONResponse:
    require_authenticated(request)
    previous = get_cpamc_settings()
    base_url = normalize_cpamc_base_url(payload.base_url)
    management_key = (payload.management_key or "").strip()
    if payload.enabled and not base_url:
        raise HTTPException(status_code=400, detail="CPAMC link is required when enabled")
    if payload.enabled and not management_key:
        raise HTTPException(status_code=400, detail="CPAMC management key is required when enabled")
    linked = previous["linked"] and previous["base_url"] == base_url and previous["management_key"] == management_key
    saved = set_cpamc_settings(
        {
            "enabled": payload.enabled,
            "base_url": base_url,
            "management_key": management_key,
            "linked": linked,
            "last_error": previous["last_error"] if linked else "",
        }
    )
    return JSONResponse({"ok": True, "cpamc": saved})


@app.post("/api/cpamc/test")
async def test_cpamc_settings(payload: CpamcSettingsPayload, request: Request) -> JSONResponse:
    require_authenticated(request)
    base_url = normalize_cpamc_base_url(payload.base_url)
    management_key = (payload.management_key or "").strip()
    if not base_url:
        raise HTTPException(status_code=400, detail="CPAMC link is required")
    if not management_key:
        raise HTTPException(status_code=400, detail="CPAMC management key is required")
    try:
        response = cpamc_request(
            "GET",
            base_url=base_url,
            management_key=management_key,
            path="config",
        )
    except requests.RequestException as exc:
        set_cpamc_settings(
            {
                "enabled": payload.enabled,
                "base_url": base_url,
                "management_key": management_key,
                "linked": False,
                "last_error": str(exc),
            }
        )
        raise HTTPException(status_code=502, detail=f"CPAMC connection failed: {exc}") from exc
    if not response.ok:
        message = parse_cpamc_error(response)
        set_cpamc_settings(
            {
                "enabled": payload.enabled,
                "base_url": base_url,
                "management_key": management_key,
                "linked": False,
                "last_error": message,
            }
        )
        raise HTTPException(status_code=502, detail=f"CPAMC test failed: {message}")
    saved = set_cpamc_settings(
        {
            "enabled": payload.enabled,
            "base_url": base_url,
            "management_key": management_key,
            "linked": True,
            "last_error": "",
        }
    )
    return JSONResponse({"ok": True, "linked": True, "cpamc": saved})


@app.post("/api/credentials")
async def create_credential(payload: CredentialCreate, request: Request) -> JSONResponse:
    require_authenticated(request)
    if payload.kind not in SUPPORTED_CREDENTIAL_KINDS:
        raise HTTPException(status_code=400, detail="Unsupported credential kind")
    if payload.kind in {"moemail", "cloudflare_temp_email"} and not (payload.base_url or "").strip():
        raise HTTPException(status_code=400, detail="Base URL is required for this credential type")
    timestamp = now_iso()
    credential_id = execute(
        """
        INSERT INTO credentials (name, kind, api_key, secret, base_url, prefix, domain, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.name.strip(),
            payload.kind,
            payload.api_key.strip(),
            (payload.secret or "").strip() or None,
            (payload.base_url or "").strip() or None,
            (payload.prefix or "").strip() or None,
            (payload.domain or "").strip() or None,
            (payload.notes or "").strip() or None,
            timestamp,
            timestamp,
        ),
    )
    return JSONResponse({"ok": True, "id": credential_id})


@app.delete("/api/credentials/{credential_id}")
async def delete_credential(credential_id: int, request: Request) -> JSONResponse:
    require_authenticated(request)
    active = fetch_one(
        """
        SELECT id FROM tasks
        WHERE (email_credential_id = ? OR captcha_credential_id = ?)
          AND status IN ('queued', 'running', 'stopping')
        """,
        (credential_id, credential_id),
    )
    if active is not None:
        raise HTTPException(status_code=409, detail="Credential is used by an active task")
    defaults = get_defaults()
    for key, value in defaults.items():
        if value == credential_id:
            set_setting(key, None)
    execute_no_return("DELETE FROM credentials WHERE id = ?", (credential_id,))
    return JSONResponse({"ok": True})


@app.post("/api/proxies")
async def create_proxy(payload: ProxyCreate, request: Request) -> JSONResponse:
    require_authenticated(request)
    timestamp = now_iso()
    proxy_url = normalize_proxy_url(payload.proxy_url)
    proxy_id = execute(
        """
        INSERT INTO proxies (name, proxy_url, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            payload.name.strip(),
            proxy_url,
            (payload.notes or "").strip() or None,
            timestamp,
            timestamp,
        ),
    )
    return JSONResponse({"ok": True, "id": proxy_id})


@app.delete("/api/proxies/{proxy_id}")
async def delete_proxy(proxy_id: int, request: Request) -> JSONResponse:
    require_authenticated(request)
    proxy = get_proxy(proxy_id)
    active = fetch_one("SELECT id FROM tasks WHERE proxy = ? AND status IN ('queued', 'running', 'stopping')", (str(proxy["proxy_url"]),))
    if active is not None:
        raise HTTPException(status_code=409, detail="Proxy is used by an active task")
    if get_defaults()["default_proxy_id"] == proxy_id:
        set_setting("default_proxy_id", None)
    execute_no_return("DELETE FROM proxies WHERE id = ?", (proxy_id,))
    return JSONResponse({"ok": True})


@app.post("/api/tasks")
async def create_task(payload: TaskCreate, request: Request) -> JSONResponse:
    require_authenticated(request)
    name, config = resolve_task_configuration(
        name=payload.name,
        platform=payload.platform,
        quantity=payload.quantity,
        concurrency=payload.concurrency,
        email_credential_id=payload.email_credential_id,
        captcha_credential_id=payload.captcha_credential_id,
        proxy_mode=payload.proxy_mode,
        proxy_id=payload.proxy_id,
        source="ui",
        auto_delete_at=None,
    )
    task_id = insert_task(name=name, config=config)
    return JSONResponse({"ok": True, "id": task_id})


@app.get("/api/tasks/{task_id}")
async def task_detail(task_id: int, request: Request) -> JSONResponse:
    require_authenticated(request)
    return JSONResponse({"task": serialize_task(get_task(task_id))})


@app.get("/api/tasks/{task_id}/console")
async def task_console(task_id: int, request: Request) -> JSONResponse:
    require_authenticated(request)
    row = get_task(task_id)
    return JSONResponse({"task_id": task_id, "console": read_tail(Path(row["console_path"]))})


@app.post("/api/tasks/{task_id}/stop")
async def stop_task(task_id: int, request: Request) -> JSONResponse:
    require_authenticated(request)
    supervisor.stop_task(task_id)
    return JSONResponse({"ok": True})


@app.post("/api/tasks/{task_id}/cpamc-import")
async def import_task_to_cpamc(task_id: int, request: Request) -> JSONResponse:
    require_authenticated(request)
    cpamc = get_cpamc_settings()
    if not cpamc["enabled"]:
        raise HTTPException(status_code=400, detail="CPAMC is not enabled")
    if not cpamc["linked"]:
        raise HTTPException(status_code=400, detail="CPAMC is not linked yet")
    if not cpamc["base_url"] or not cpamc["management_key"]:
        raise HTTPException(status_code=400, detail="CPAMC configuration is incomplete")

    task = get_task(task_id)
    candidates = cpamc_import_candidates(task, validate=True)
    if not candidates:
        raise HTTPException(status_code=400, detail="No importable JSON files were found for this task")

    imported: list[str] = []
    failed: list[dict[str, str]] = []
    for file_path in candidates:
        try:
            payload_bytes = file_path.read_bytes()
        except Exception as exc:
            failed.append({"name": file_path.name, "error": str(exc)})
            continue
        try:
            response = cpamc_request(
                "POST",
                base_url=str(cpamc["base_url"]),
                management_key=str(cpamc["management_key"]),
                path=f"auth-files?name={quote(file_path.name)}",
                data=payload_bytes,
                headers={"Content-Type": "application/json"},
            )
        except requests.RequestException as exc:
            failed.append({"name": file_path.name, "error": str(exc)})
            continue
        if response.ok:
            imported.append(file_path.name)
        else:
            failed.append({"name": file_path.name, "error": parse_cpamc_error(response)})

    if not imported:
        first_error = failed[0]["error"] if failed else "Unknown import error"
        raise HTTPException(status_code=502, detail=f"CPAMC import failed: {first_error}")
    return JSONResponse(
        {
            "ok": True,
            "imported_count": len(imported),
            "failed_count": len(failed),
            "imported": imported,
            "failed": failed,
        }
    )


@app.get("/api/tasks/{task_id}/download")
async def download_task(task_id: int, request: Request) -> FileResponse:
    require_authenticated(request)
    row = get_task(task_id)
    archive_path = create_archive(row)
    return FileResponse(path=archive_path, media_type="application/zip", filename=f"task_{task_id}_{row['platform']}.zip")


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: int, request: Request) -> JSONResponse:
    require_authenticated(request)
    row = get_task(task_id)
    if row["status"] in {"queued", "running", "stopping"}:
        raise HTTPException(status_code=409, detail="Stop the task before deleting it")
    paths = task_paths(row)
    try:
        shutil.rmtree(paths["task_dir"], ignore_errors=True)
    except Exception:
        pass
    if paths["archive_path"].exists():
        try:
            paths["archive_path"].unlink()
        except Exception:
            pass
    execute_no_return("DELETE FROM tasks WHERE id = ?", (task_id,))
    return JSONResponse({"ok": True})


@app.post("/api/schedules")
async def create_schedule(payload: ScheduleCreate, request: Request) -> JSONResponse:
    require_authenticated(request)
    validate_platform(payload.platform)
    timestamp = now_iso()
    schedule_id = execute(
        """
        INSERT INTO schedules (name, platform, quantity, concurrency, time_of_day, use_proxy, enabled, last_run_date, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
        """,
        (
            payload.name.strip(),
            payload.platform,
            payload.quantity,
            payload.concurrency,
            payload.time_of_day,
            1 if payload.use_proxy else 0,
            1 if payload.enabled else 0,
            timestamp,
            timestamp,
        ),
    )
    return JSONResponse({"ok": True, "id": schedule_id})


@app.post("/api/schedules/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: int, request: Request) -> JSONResponse:
    require_authenticated(request)
    row = get_schedule(schedule_id)
    next_value = 0 if int(row["enabled"]) else 1
    execute_no_return("UPDATE schedules SET enabled = ?, updated_at = ? WHERE id = ?", (next_value, now_iso(), schedule_id))
    return JSONResponse({"ok": True})


@app.delete("/api/schedules/{schedule_id}")
async def delete_schedule(schedule_id: int, request: Request) -> JSONResponse:
    require_authenticated(request)
    execute_no_return("DELETE FROM schedules WHERE id = ?", (schedule_id,))
    return JSONResponse({"ok": True})


@app.post("/api/api-keys")
async def create_api_key(payload: ApiKeyCreate, request: Request) -> JSONResponse:
    require_authenticated(request)
    raw_key, key_hash, prefix = generate_api_key_secret()
    key_id = execute(
        """
        INSERT INTO api_keys (name, key_hash, key_prefix, is_active, created_at, last_used_at)
        VALUES (?, ?, ?, 1, ?, NULL)
        """,
        (payload.name.strip(), key_hash, prefix, now_iso()),
    )
    return JSONResponse({"ok": True, "id": key_id, "api_key": raw_key})


@app.delete("/api/api-keys/{key_id}")
async def delete_api_key(key_id: int, request: Request) -> JSONResponse:
    require_authenticated(request)
    execute_no_return("DELETE FROM api_keys WHERE id = ?", (key_id,))
    return JSONResponse({"ok": True})


@app.post("/api/external/tasks")
async def external_create_task(payload: ExternalTaskCreate, request: Request) -> JSONResponse:
    require_api_key(request)
    auto_delete_at = date_iso(now() + timedelta(hours=24))
    task_name = payload.name or f"api-{payload.platform}-{now().strftime('%Y%m%d-%H%M%S')}"
    proxy_mode = "default" if payload.use_proxy else "none"
    _, config = resolve_task_configuration(
        name=task_name,
        platform=payload.platform,
        quantity=payload.quantity,
        concurrency=payload.concurrency,
        email_credential_id=None,
        captcha_credential_id=None,
        proxy_mode=proxy_mode,
        proxy_id=None,
        source="api",
        auto_delete_at=auto_delete_at,
    )
    task_id = insert_task(name=task_name, config=config)
    return JSONResponse({"ok": True, "task_id": task_id, "auto_delete_at": auto_delete_at})


@app.get("/api/external/tasks/{task_id}")
async def external_task_status(task_id: int, request: Request) -> JSONResponse:
    require_api_key(request)
    row = get_task(task_id)
    if row["source"] != "api":
        raise HTTPException(status_code=404, detail="API task not found")
    item = serialize_task(row)
    payload = {
        "task_id": task_id,
        "status": item["status"],
        "completed_count": item["results_count"],
        "target_quantity": item["quantity"],
        "auto_delete_at": item["auto_delete_at"],
        "download_url": None,
    }
    if item["status"] not in {"queued", "running", "stopping"}:
        payload["download_url"] = f"/api/external/tasks/{task_id}/download"
    return JSONResponse(payload)


@app.get("/api/external/tasks/{task_id}/download")
async def external_download_task(task_id: int, request: Request) -> FileResponse:
    require_api_key(request)
    row = get_task(task_id)
    if row["source"] != "api":
        raise HTTPException(status_code=404, detail="API task not found")
    archive_path = create_archive(row)
    return FileResponse(path=archive_path, media_type="application/zip", filename=f"api_task_{task_id}_{row['platform']}.zip")
