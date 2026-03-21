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

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field


ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = WEB_DIR / "runtime"
TASKS_DIR = RUNTIME_DIR / "tasks"
DB_PATH = RUNTIME_DIR / "app.db"
SESSION_COOKIE = "register_console_session"
SESSION_TTL_HOURS = max(1, int(os.getenv("WEB_CONSOLE_SESSION_TTL_HOURS", "24")))
MAX_CONCURRENT_TASKS = max(1, int(os.getenv("WEB_CONSOLE_MAX_CONCURRENT_TASKS", "2")))
POLL_INTERVAL_SECONDS = max(1.0, float(os.getenv("WEB_CONSOLE_POLL_INTERVAL", "2.0")))

PROXY_PROVIDER_KEYS = {
    "proxy-free.com": "Proxy-Free Premium API",
    "openproxylist.com": "OpenProxyList",
}

PLATFORMS = {
    "openai-register": {
        "label": "OpenAI Register",
        "requires_email_credential": True,
        "requires_captcha_credential": False,
        "supports_proxy": True,
        "default_concurrency": 1,
        "notes": "Uses GPTMail and writes token/account files into the task directory.",
    },
    "openai-register-bate-L": {
        "label": "OpenAl Register L临时版本",
        "requires_email_credential": True,
        "requires_captcha_credential": False,
        "supports_proxy": True,
        "default_concurrency": 1,
        "notes": "Uses GPTMail and writes token/account files into the task directory.",
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
        "nav_proxy_pool": "代理池",
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
        "panel_defaults_desc": "API 创建任务时会优先使用这里的默认凭据和默认代理。",
        "default_gptmail": "默认 GPTMail",
        "default_yescaptcha": "默认 YesCaptcha",
        "default_proxy": "默认代理",
        "save_defaults": "保存默认设置",
        "panel_recent_tasks_title": "最近任务",
        "panel_recent_tasks_desc": "点任意任务可直接跳到详情页查看控制台输出。",
        "section_credentials": "凭据管理",
        "credentials_create_title": "新增凭据",
        "credentials_create_desc": "支持 GPTMail 与 YesCaptcha，保存后可直接设为默认。",
        "gptmail_optional_hint": "GPTMail 的 Base URL、邮箱前缀、邮箱域名都有默认值，可直接留空不填写。",
        "credentials_saved_title": "已保存凭据",
        "credentials_saved_desc": "支持删除、查看备注、设为默认。",
        "field_name": "名称",
        "field_kind": "类型",
        "field_api_key": "API Key",
        "field_base_url": "Base URL",
        "field_prefix": "邮箱前缀",
        "field_domain": "邮箱域名",
        "field_base_url_placeholder": "留空使用默认 Base URL",
        "field_prefix_placeholder": "留空使用默认邮箱前缀",
        "field_domain_placeholder": "留空使用默认邮箱域名",
        "field_notes": "备注",
        "save_credential": "保存凭据",
        "section_proxies": "代理管理",
        "section_proxy_pool": "代理池",
        "proxies_create_title": "新增代理",
        "proxies_create_desc": "支持保存多个代理，并可指定为站点默认代理。",
        "proxies_saved_title": "已保存代理",
        "proxies_saved_desc": "任务可选择默认代理、指定代理或不使用代理。",
        "proxies_group_assign_title": "加入代理组",
        "proxies_group_assign_desc": "可从手动代理中多选后批量加入已有代理组。",
        "proxy_groups_title": "代理组",
        "proxy_groups_desc": "将多个代理组合在一起，任务可按轮询模式自动切换。",
        "proxy_pool_provider_title": "供应商设置",
        "proxy_pool_provider_desc": "在这里配置站点 Token 与筛选条件，再同步代理池数据。",
        "proxy_pool_list_title": "代理池列表",
        "proxy_pool_list_desc": "支持多选代理并批量加入代理组。",
        "field_provider_token": "API Token",
        "field_proxy_group_select": "选择代理组",
        "field_proxy_group_name": "代理组名称",
        "field_protocol": "协议类型",
        "field_country": "国家",
        "field_region": "区域/搜索",
        "field_anonymity": "匿名级别",
        "field_min_speed": "最低速度",
        "field_min_uptime": "最低在线率",
        "field_sort_by": "排序字段",
        "field_is_working": "仅同步可用代理",
        "proxy_mode_group": "代理组轮询",
        "proxy_mode_provider": "Proxy-Free API",
        "save_proxy_group": "保存代理组",
        "save_provider_settings": "保存供应商设置",
        "sync_proxy_pool": "同步代理池",
        "add_selected_to_group": "选中加入代理组",
        "choose_proxy_group": "选择一个代理组",
        "empty_proxy_groups": "暂无代理组",
        "empty_proxy_pool": "代理池暂无数据",
        "provider_status_ready": "已配置",
        "provider_status_empty": "未配置",
        "proxy_group_mode_hint": "选择代理组后，任务会按轮询方式自动切换代理地址。",
        "proxy_provider_mode_hint": "根据代理池中保存的 Proxy-Free 配置即时拉取一个代理。",
        "delete_proxy_group_confirm": "删除代理组 {name}？",
        "proxy_group_meta": "{count} 个代理 | 创建于 {created_at}",
        "pool_item_meta": "{source} | {protocol} | {country} | {status}",
        "proxy_pool_sync_done": "代理池同步完成，共导入 {count} 条代理。",
        "proxy_pool_filter_keyword": "搜索代理 / 国家 / 来源",
        "proxy_pool_filter_protocol": "筛选协议",
        "proxy_pool_filter_country": "筛选国家",
        "proxy_pool_filter_source": "筛选来源",
        "proxy_pool_filter_working": "仅看可用",
        "proxy_pool_speed": "速度",
        "proxy_pool_uptime": "在线率",
        "proxy_pool_country": "国家",
        "proxy_pool_protocol": "协议",
        "proxy_pool_source": "来源",
        "proxy_group_detail_title": "代理组详情",
        "proxy_group_detail_desc": "查看成员、移除代理、拖动调整轮询顺序。",
        "remove_group_member": "移除成员",
        "move_up": "上移",
        "move_down": "下移",
        "save_group_order": "保存排序",
        "group_member_meta": "{source} | {label}",
        "empty_group_members": "当前代理组还没有成员",
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
        "section_api": "API 接口",
        "api_create_title": "创建 API Key",
        "api_create_desc": "新建成功后只会显示一次，请立即保存。",
        "api_saved_title": "已有 API Key",
        "api_saved_desc": "可用于外部程序调用创建任务、查询状态和下载结果。",
        "save_api_key": "生成 API Key",
        "section_docs": "API文档",
        "docs_intro_title": "总览",
        "docs_intro_desc": "控制台支持网页操作和外部 API 调用。外部 API 默认使用站点中已配置的默认 GPTMail、默认 YesCaptcha 和默认代理。通过 API 创建的任务会在完成 24 小时后自动清理。",
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
        "param_platform_desc": "驱动名称，目前支持 `openai-register`、`openai-register-bate-L` 和 `grok-register`",
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
        "use_default_gptmail": "使用默认 GPTMail",
        "use_default_yescaptcha": "使用默认 YesCaptcha",
        "choose_proxy": "选择一个代理",
        "no_default_gptmail": "不设置默认 GPTMail",
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
        "nav_proxy_pool": "Proxy Pool",
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
        "panel_defaults_desc": "API-created tasks will use these default credentials and proxy settings first.",
        "default_gptmail": "Default GPTMail",
        "default_yescaptcha": "Default YesCaptcha",
        "default_proxy": "Default proxy",
        "save_defaults": "Save defaults",
        "panel_recent_tasks_title": "Recent tasks",
        "panel_recent_tasks_desc": "Click any task to jump straight into the detail view and console output.",
        "section_credentials": "Credential Management",
        "credentials_create_title": "Add credential",
        "credentials_create_desc": "Supports GPTMail and YesCaptcha. You can set the saved item as default immediately.",
        "gptmail_optional_hint": "For GPTMail, Base URL, email prefix, and email domain all have defaults, so you can leave them blank.",
        "credentials_saved_title": "Saved credentials",
        "credentials_saved_desc": "Delete, review notes, and set defaults here.",
        "field_name": "Name",
        "field_kind": "Type",
        "field_api_key": "API Key",
        "field_base_url": "Base URL",
        "field_prefix": "Email prefix",
        "field_domain": "Email domain",
        "field_base_url_placeholder": "Leave blank to use the default Base URL",
        "field_prefix_placeholder": "Leave blank to use the default email prefix",
        "field_domain_placeholder": "Leave blank to use the default email domain",
        "field_notes": "Notes",
        "save_credential": "Save credential",
        "section_proxies": "Proxy Management",
        "section_proxy_pool": "Proxy Pool",
        "proxies_create_title": "Add proxy",
        "proxies_create_desc": "Save multiple proxies and promote one as the site-wide default.",
        "proxies_saved_title": "Saved proxies",
        "proxies_saved_desc": "Tasks can use the default proxy, a specific proxy, or no proxy at all.",
        "proxies_group_assign_title": "Add To Proxy Group",
        "proxies_group_assign_desc": "Multi-select saved proxies and batch assign them to an existing group.",
        "proxy_groups_title": "Proxy Groups",
        "proxy_groups_desc": "Combine multiple proxies so tasks can rotate through them automatically.",
        "proxy_pool_provider_title": "Provider Settings",
        "proxy_pool_provider_desc": "Configure tokens and filters here before syncing provider data.",
        "proxy_pool_list_title": "Proxy Pool Entries",
        "proxy_pool_list_desc": "Select multiple pool proxies and add them to a proxy group.",
        "field_provider_token": "API Token",
        "field_proxy_group_select": "Proxy group",
        "field_proxy_group_name": "Group name",
        "field_protocol": "Protocol",
        "field_country": "Country",
        "field_region": "Region/Search",
        "field_anonymity": "Anonymity",
        "field_min_speed": "Min speed",
        "field_min_uptime": "Min uptime",
        "field_sort_by": "Sort by",
        "field_is_working": "Working only",
        "proxy_mode_group": "Rotate proxy group",
        "proxy_mode_provider": "Proxy-Free API",
        "save_proxy_group": "Save proxy group",
        "save_provider_settings": "Save provider settings",
        "sync_proxy_pool": "Sync proxy pool",
        "add_selected_to_group": "Add selected to group",
        "choose_proxy_group": "Choose a proxy group",
        "empty_proxy_groups": "No proxy groups yet",
        "empty_proxy_pool": "No proxy pool entries yet",
        "provider_status_ready": "Configured",
        "provider_status_empty": "Not configured",
        "proxy_group_mode_hint": "When a proxy group is selected, tasks rotate through its proxy URLs.",
        "proxy_provider_mode_hint": "Fetch a proxy instantly using the saved Proxy-Free filters.",
        "delete_proxy_group_confirm": "Delete proxy group {name}?",
        "proxy_group_meta": "{count} proxies | Created at {created_at}",
        "pool_item_meta": "{source} | {protocol} | {country} | {status}",
        "proxy_pool_sync_done": "Proxy pool sync finished. Imported {count} proxies.",
        "proxy_pool_filter_keyword": "Search proxy / country / source",
        "proxy_pool_filter_protocol": "Filter protocol",
        "proxy_pool_filter_country": "Filter country",
        "proxy_pool_filter_source": "Filter source",
        "proxy_pool_filter_working": "Working only",
        "proxy_pool_speed": "Speed",
        "proxy_pool_uptime": "Uptime",
        "proxy_pool_country": "Country",
        "proxy_pool_protocol": "Protocol",
        "proxy_pool_source": "Source",
        "proxy_group_detail_title": "Proxy Group Detail",
        "proxy_group_detail_desc": "Review members, remove proxies, and reorder the rotation list.",
        "remove_group_member": "Remove member",
        "move_up": "Move up",
        "move_down": "Move down",
        "save_group_order": "Save order",
        "group_member_meta": "{source} | {label}",
        "empty_group_members": "This proxy group has no members yet",
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
        "section_api": "API 接口",
        "api_create_title": "Create API key",
        "api_create_desc": "A new key is only shown once. Save it immediately.",
        "api_saved_title": "Existing API keys",
        "api_saved_desc": "Use these keys from external services to create tasks, query status, and download results.",
        "save_api_key": "Generate API key",
        "section_docs": "API Docs",
        "docs_intro_title": "总览",
        "docs_intro_desc": "控制台支持网页操作和外部 API 调用。外部 API 默认使用站点中已配置的默认 GPTMail、默认 YesCaptcha 和默认代理。通过 API 创建的任务会在完成 24 小时后自动清理。",
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
        "param_platform_desc": "Driver name. Supported values: `openai-register`, `openai-register-bate-L`, and `grok-register`",
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
        "use_default_gptmail": "Use default GPTMail",
        "use_default_yescaptcha": "Use default YesCaptcha",
        "choose_proxy": "Choose a proxy",
        "no_default_gptmail": "No default GPTMail",
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

            CREATE TABLE IF NOT EXISTS proxy_provider_settings (
                provider_key TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                api_token TEXT,
                config_json TEXT NOT NULL DEFAULT '{}',
                last_synced_at TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS proxy_pool_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_key TEXT NOT NULL,
                remote_id TEXT,
                proxy_url TEXT NOT NULL,
                ip_address TEXT,
                port INTEGER,
                protocol TEXT,
                country_code TEXT,
                country_name TEXT,
                anonymity TEXT,
                speed REAL,
                uptime REAL,
                is_working INTEGER NOT NULL DEFAULT 1,
                source_label TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(provider_key, proxy_url)
            );

            CREATE TABLE IF NOT EXISTS proxy_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS proxy_group_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                proxy_url TEXT NOT NULL,
                label TEXT,
                source_type TEXT NOT NULL DEFAULT 'manual',
                proxy_id INTEGER,
                pool_item_id INTEGER,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(group_id, proxy_url),
                FOREIGN KEY(group_id) REFERENCES proxy_groups(id)
            );

            CREATE TABLE IF NOT EXISTS proxy_group_states (
                group_id INTEGER PRIMARY KEY,
                next_index INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(group_id) REFERENCES proxy_groups(id)
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
            "tasks",
            {
                "source": "TEXT NOT NULL DEFAULT 'ui'",
                "auto_delete_at": "TEXT",
            },
        )
        ensure_columns(
            conn,
            "schedules",
            {
                "proxy_mode": "TEXT NOT NULL DEFAULT 'none'",
                "proxy_id": "INTEGER",
                "proxy_group_id": "INTEGER",
            },
        )
        ensure_columns(
            conn,
            "proxy_group_members",
            {
                "sort_order": "INTEGER NOT NULL DEFAULT 0",
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


def get_credentials() -> list[dict[str, Any]]:
    return [row_to_dict(row) for row in fetch_all("SELECT * FROM credentials ORDER BY kind, name")]


def get_proxies() -> list[dict[str, Any]]:
    return [row_to_dict(row) for row in fetch_all("SELECT * FROM proxies ORDER BY name")]


def get_proxy_provider_settings() -> list[dict[str, Any]]:
    rows = fetch_all("SELECT * FROM proxy_provider_settings ORDER BY provider_key ASC")
    items: list[dict[str, Any]] = []
    known = {**{key: None for key in PROXY_PROVIDER_KEYS}, **{str(row["provider_key"]): row for row in rows}}
    for provider_key in PROXY_PROVIDER_KEYS:
        row = known.get(provider_key)
        if row is None:
            items.append(
                {
                    "provider_key": provider_key,
                    "provider_label": PROXY_PROVIDER_KEYS[provider_key],
                    "enabled": True,
                    "api_token": "",
                    "config": {},
                    "last_synced_at": None,
                    "last_error": None,
                    "is_configured": False,
                }
            )
            continue
        item = row_to_dict(row)
        try:
            item["config"] = json.loads(item.get("config_json") or "{}")
        except Exception:
            item["config"] = {}
        item["provider_label"] = PROXY_PROVIDER_KEYS.get(provider_key, provider_key)
        item["is_configured"] = bool(item.get("api_token")) if provider_key == "proxy-free.com" else True
        items.append(item)
    return items


def get_proxy_pool_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in fetch_all("SELECT * FROM proxy_pool_items ORDER BY updated_at DESC, id DESC"):
        item = row_to_dict(row)
        try:
            item["metadata"] = json.loads(item.get("metadata_json") or "{}")
        except Exception:
            item["metadata"] = {}
        items.append(item)
    return items


def get_proxy_group(group_id: int) -> sqlite3.Row:
    row = fetch_one("SELECT * FROM proxy_groups WHERE id = ?", (group_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Proxy group not found")
    return row


def get_proxy_groups() -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for row in fetch_all("SELECT * FROM proxy_groups ORDER BY name ASC"):
        item = row_to_dict(row)
        members = [row_to_dict(member) for member in fetch_all("SELECT * FROM proxy_group_members WHERE group_id = ? ORDER BY sort_order ASC, id ASC", (int(row["id"]),))]
        for member in members:
            if member.get("pool_item_id"):
                pool_row = fetch_one("SELECT protocol, country_code, country_name, source_label, speed, uptime FROM proxy_pool_items WHERE id = ?", (int(member["pool_item_id"]),))
                if pool_row is not None:
                    member["pool_protocol"] = pool_row["protocol"]
                    member["pool_country_code"] = pool_row["country_code"]
                    member["pool_country_name"] = pool_row["country_name"]
                    member["pool_source_label"] = pool_row["source_label"]
                    member["pool_speed"] = pool_row["speed"]
                    member["pool_uptime"] = pool_row["uptime"]
        item["members"] = members
        item["count"] = len(members)
        groups.append(item)
    return groups


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


def validate_proxy_provider(provider_key: str) -> str:
    if provider_key not in PROXY_PROVIDER_KEYS:
        raise HTTPException(status_code=400, detail="Unsupported proxy provider")
    return provider_key


def sanitize_provider_config(payload: ProxyProviderSettingsPayload) -> dict[str, Any]:
    return {
        "country": (payload.country or "").strip() or None,
        "region": (payload.region or "").strip() or None,
        "protocol": (payload.protocol or "").strip().upper() or None,
        "anonymity": (payload.anonymity or "").strip() or None,
        "min_speed": payload.min_speed,
        "min_uptime": payload.min_uptime,
        "is_working": bool(payload.is_working),
        "sort_by": (payload.sort_by or "").strip() or None,
        "per_page": payload.per_page,
    }


def save_proxy_provider_settings(payload: ProxyProviderSettingsPayload) -> None:
    provider_key = validate_proxy_provider(payload.provider_key)
    timestamp = now_iso()
    config = sanitize_provider_config(payload)
    execute_no_return(
        """
        INSERT INTO proxy_provider_settings (provider_key, enabled, api_token, config_json, last_synced_at, last_error, created_at, updated_at)
        VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)
        ON CONFLICT(provider_key) DO UPDATE SET
            enabled = excluded.enabled,
            api_token = excluded.api_token,
            config_json = excluded.config_json,
            updated_at = excluded.updated_at
        """,
        (
            provider_key,
            1 if payload.enabled else 0,
            (payload.api_token or "").strip() or None,
            json.dumps(config, ensure_ascii=False),
            timestamp,
            timestamp,
        ),
    )


def get_proxy_provider_setting(provider_key: str) -> dict[str, Any]:
    validate_proxy_provider(provider_key)
    for item in get_proxy_provider_settings():
        if item["provider_key"] == provider_key:
            return item
    raise HTTPException(status_code=404, detail="Proxy provider not found")


def make_proxy_url(protocol: str | None, ip_address: str | None, port: int | None) -> str | None:
    if not ip_address or not port:
        return None
    scheme = (protocol or "http").strip().lower()
    if scheme == "https":
        scheme = "http"
    return f"{scheme}://{ip_address}:{int(port)}"


def upsert_pool_item(*, provider_key: str, proxy_url: str, remote_id: str | None, ip_address: str | None, port: int | None, protocol: str | None, country_code: str | None, country_name: str | None, anonymity: str | None, speed: float | None, uptime: float | None, is_working: bool, source_label: str, metadata: dict[str, Any]) -> None:
    timestamp = now_iso()
    execute_no_return(
        """
        INSERT INTO proxy_pool_items (
            provider_key, remote_id, proxy_url, ip_address, port, protocol, country_code, country_name,
            anonymity, speed, uptime, is_working, source_label, metadata_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(provider_key, proxy_url) DO UPDATE SET
            remote_id = excluded.remote_id,
            ip_address = excluded.ip_address,
            port = excluded.port,
            protocol = excluded.protocol,
            country_code = excluded.country_code,
            country_name = excluded.country_name,
            anonymity = excluded.anonymity,
            speed = excluded.speed,
            uptime = excluded.uptime,
            is_working = excluded.is_working,
            source_label = excluded.source_label,
            metadata_json = excluded.metadata_json,
            updated_at = excluded.updated_at
        """,
        (
            provider_key,
            remote_id,
            proxy_url,
            ip_address,
            port,
            protocol,
            country_code,
            country_name,
            anonymity,
            speed,
            uptime,
            1 if is_working else 0,
            source_label,
            json.dumps(metadata, ensure_ascii=False),
            timestamp,
            timestamp,
        ),
    )


def sync_proxy_free_provider() -> int:
    settings = get_proxy_provider_setting("proxy-free.com")
    token = (settings.get("api_token") or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Proxy-Free API token is not configured")
    config = settings.get("config") or {}
    params: dict[str, Any] = {"per_page": int(config.get("per_page") or 50)}
    if config.get("protocol"):
        params["protocol"] = config["protocol"]
    if config.get("country"):
        params["country"] = config["country"]
    if config.get("region"):
        params["search"] = config["region"]
    if config.get("anonymity"):
        params["anonymity"] = config["anonymity"]
    if config.get("min_speed") is not None:
        params["min_speed"] = config["min_speed"]
    if config.get("min_uptime") is not None:
        params["min_uptime"] = config["min_uptime"]
    if config.get("is_working"):
        params["is_working"] = "true"
    if config.get("sort_by"):
        params["sort_by"] = config["sort_by"]
    response = requests.get(
        "https://proxy-free.com/api/v1/premium-proxies/",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") or []
    imported = 0
    for entry in data:
        protocol = str(entry.get("protocol") or "HTTP").upper()
        country = entry.get("country") or {}
        proxy_url = make_proxy_url(protocol, entry.get("ip_address"), entry.get("port"))
        if not proxy_url:
            continue
        upsert_pool_item(
            provider_key="proxy-free.com",
            proxy_url=proxy_url,
            remote_id=str(entry.get("id")) if entry.get("id") is not None else None,
            ip_address=entry.get("ip_address"),
            port=int(entry.get("port")) if entry.get("port") is not None else None,
            protocol=protocol,
            country_code=country.get("code"),
            country_name=country.get("name"),
            anonymity=entry.get("anonymity"),
            speed=float(entry.get("speed")) if entry.get("speed") is not None else None,
            uptime=float(entry.get("uptime")) if entry.get("uptime") is not None else None,
            is_working=bool(entry.get("is_working")),
            source_label=PROXY_PROVIDER_KEYS["proxy-free.com"],
            metadata=entry,
        )
        imported += 1
    execute_no_return(
        "UPDATE proxy_provider_settings SET last_synced_at = ?, last_error = NULL WHERE provider_key = ?",
        (now_iso(), "proxy-free.com"),
    )
    return imported


def sync_openproxylist_provider() -> int:
    imported = 0
    sources = {
        "HTTP": "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS.txt",
        "SOCKS4": "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS4.txt",
        "SOCKS5": "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5.txt",
    }
    for protocol, url in sources.items():
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        for raw_line in response.text.splitlines():
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            host, _, port_raw = line.rpartition(":")
            if not host or not port_raw.isdigit():
                continue
            proxy_url = make_proxy_url(protocol, host, int(port_raw))
            if not proxy_url:
                continue
            upsert_pool_item(
                provider_key="openproxylist.com",
                proxy_url=proxy_url,
                remote_id=None,
                ip_address=host,
                port=int(port_raw),
                protocol=protocol,
                country_code=None,
                country_name=None,
                anonymity=None,
                speed=None,
                uptime=None,
                is_working=True,
                source_label=PROXY_PROVIDER_KEYS["openproxylist.com"],
                metadata={"source_url": url},
            )
            imported += 1
    row = fetch_one("SELECT 1 FROM proxy_provider_settings WHERE provider_key = ?", ("openproxylist.com",))
    if row is None:
        execute_no_return(
            "INSERT INTO proxy_provider_settings (provider_key, enabled, api_token, config_json, last_synced_at, last_error, created_at, updated_at) VALUES (?, 1, NULL, '{}', ?, NULL, ?, ?)",
            ("openproxylist.com", now_iso(), now_iso(), now_iso()),
        )
    else:
        execute_no_return(
            "UPDATE proxy_provider_settings SET last_synced_at = ?, last_error = NULL, updated_at = ? WHERE provider_key = ?",
            (now_iso(), now_iso(), "openproxylist.com"),
        )
    return imported


def sync_proxy_provider(provider_key: str) -> int:
    validate_proxy_provider(provider_key)
    try:
        if provider_key == "proxy-free.com":
            return sync_proxy_free_provider()
        if provider_key == "openproxylist.com":
            return sync_openproxylist_provider()
    except requests.RequestException as exc:
        execute_no_return(
            "UPDATE proxy_provider_settings SET last_error = ?, updated_at = ? WHERE provider_key = ?",
            (str(exc), now_iso(), provider_key),
        )
        raise HTTPException(status_code=502, detail=f"Provider sync failed: {exc}")
    raise HTTPException(status_code=400, detail="Unsupported proxy provider")


def add_group_members(*, group_id: int, proxy_urls: list[str], proxy_ids: list[int], pool_item_ids: list[int]) -> None:
    timestamp = now_iso()
    seen: set[str] = set()
    max_order_row = fetch_one("SELECT COALESCE(MAX(sort_order), -1) AS max_order FROM proxy_group_members WHERE group_id = ?", (group_id,))
    next_order = int(max_order_row["max_order"]) + 1 if max_order_row is not None else 0

    def insert_member(proxy_url: str, label: str | None, source_type: str, proxy_id: int | None, pool_item_id: int | None) -> None:
        nonlocal next_order
        normalized = proxy_url.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        execute_no_return(
            "INSERT OR IGNORE INTO proxy_group_members (group_id, proxy_url, label, source_type, proxy_id, pool_item_id, sort_order, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (group_id, normalized, label, source_type, proxy_id, pool_item_id, next_order, timestamp),
        )
        next_order += 1

    for value in proxy_urls:
        normalized = value.strip()
        if normalized:
            insert_member(normalized, normalized, "manual", None, None)
    for proxy_id in proxy_ids:
        proxy = get_proxy(proxy_id)
        insert_member(str(proxy["proxy_url"]), str(proxy["name"]), "manual_saved", int(proxy["id"]), None)
    for pool_item_id in pool_item_ids:
        row = fetch_one("SELECT * FROM proxy_pool_items WHERE id = ?", (pool_item_id,))
        if row is None:
            continue
        insert_member(str(row["proxy_url"]), str(row["source_label"] or row["proxy_url"]), "pool", None, int(row["id"]))


def get_next_proxy_from_group(group_id: int) -> str:
    members = fetch_all("SELECT * FROM proxy_group_members WHERE group_id = ? ORDER BY sort_order ASC, id ASC", (group_id,))
    if not members:
        raise HTTPException(status_code=400, detail="Selected proxy group has no members")
    state = fetch_one("SELECT * FROM proxy_group_states WHERE group_id = ?", (group_id,))
    next_index = int(state["next_index"]) if state is not None else 0
    member = members[next_index % len(members)]
    new_index = (next_index + 1) % len(members)
    timestamp = now_iso()
    execute_no_return(
        "INSERT INTO proxy_group_states (group_id, next_index, updated_at) VALUES (?, ?, ?) ON CONFLICT(group_id) DO UPDATE SET next_index = excluded.next_index, updated_at = excluded.updated_at",
        (group_id, new_index, timestamp),
    )
    return str(member["proxy_url"])


def get_proxy_group_member(group_id: int, member_id: int) -> sqlite3.Row:
    row = fetch_one("SELECT * FROM proxy_group_members WHERE group_id = ? AND id = ?", (group_id, member_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Proxy group member not found")
    return row


def reorder_proxy_group_members(group_id: int, member_ids: list[int]) -> None:
    members = fetch_all("SELECT id FROM proxy_group_members WHERE group_id = ? ORDER BY sort_order ASC, id ASC", (group_id,))
    existing_ids = [int(row["id"]) for row in members]
    if sorted(existing_ids) != sorted(member_ids):
        raise HTTPException(status_code=400, detail="Member order does not match current proxy group members")
    timestamp = now_iso()
    for index, member_id in enumerate(member_ids):
        execute_no_return(
            "UPDATE proxy_group_members SET sort_order = ? WHERE group_id = ? AND id = ?",
            (index, group_id, member_id),
        )
    execute_no_return(
        "UPDATE proxy_groups SET updated_at = ? WHERE id = ?",
        (timestamp, group_id),
    )


def get_task(task_id: int) -> sqlite3.Row:
    row = fetch_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return row


def resolve_required_credential(kind: str, credential_id: int | None) -> sqlite3.Row:
    defaults = get_defaults()
    selected_id = credential_id
    if selected_id is None:
        selected_id = defaults["default_gptmail_credential_id"] if kind == "gptmail" else defaults["default_yescaptcha_credential_id"]
    if selected_id is None:
        raise HTTPException(status_code=400, detail=f"No default {kind} credential is configured")
    credential = get_credential(int(selected_id))
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
        return str(get_proxy(int(selected))["proxy_url"])
    if mode == "custom":
        if proxy_id is None:
            raise HTTPException(status_code=400, detail="A proxy must be selected")
        return str(get_proxy(proxy_id)["proxy_url"])
    raise HTTPException(status_code=400, detail="Unsupported proxy mode")


def resolve_proxy_selection(proxy_mode: str, proxy_id: int | None, proxy_group_id: int | None) -> str | None:
    mode = proxy_mode or "none"
    if mode in {"none", "default", "custom"}:
        return resolve_proxy_value(mode, proxy_id)
    if mode == "group":
        if proxy_group_id is None:
            raise HTTPException(status_code=400, detail="A proxy group must be selected")
        get_proxy_group(proxy_group_id)
        return get_next_proxy_from_group(proxy_group_id)
    if mode == "provider":
        imported = sync_proxy_provider("proxy-free.com")
        if imported <= 0:
            raise HTTPException(status_code=400, detail="Proxy-Free returned no proxies")
        row = fetch_one(
            "SELECT * FROM proxy_pool_items WHERE provider_key = 'proxy-free.com' AND is_working = 1 ORDER BY updated_at DESC, id DESC LIMIT 1"
        )
        if row is None:
            raise HTTPException(status_code=400, detail="No Proxy-Free proxy is available")
        return str(row["proxy_url"])
    raise HTTPException(status_code=400, detail="Unsupported proxy mode")


def task_paths(task: sqlite3.Row | dict[str, Any]) -> dict[str, Path]:
    task_dir = Path(task["task_dir"])
    if task["platform"] in {"openai-register", "openai-register-bate-L"}:
        results_file = task_dir / "output" / "tokens" / "accounts.txt"
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
    base_url: str | None = None
    prefix: str | None = None
    domain: str | None = None
    notes: str | None = None


class ProxyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    proxy_url: str = Field(min_length=1, max_length=300)
    notes: str | None = None


class ProxyProviderSettingsPayload(BaseModel):
    provider_key: str
    enabled: bool = True
    api_token: str | None = None
    country: str | None = None
    region: str | None = None
    protocol: str | None = None
    anonymity: str | None = None
    min_speed: float | None = None
    min_uptime: float | None = None
    is_working: bool = True
    sort_by: str | None = None
    per_page: int = Field(default=50, ge=1, le=100)


class ProxyPoolSyncPayload(BaseModel):
    provider_key: str


class ProxyGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    notes: str | None = None
    proxy_urls: list[str] = Field(default_factory=list)
    proxy_ids: list[int] = Field(default_factory=list)
    pool_item_ids: list[int] = Field(default_factory=list)


class ProxyGroupAssignPayload(BaseModel):
    group_id: int
    proxy_urls: list[str] = Field(default_factory=list)
    proxy_ids: list[int] = Field(default_factory=list)
    pool_item_ids: list[int] = Field(default_factory=list)


class ProxyGroupMemberOrderPayload(BaseModel):
    member_ids: list[int] = Field(min_length=1)


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    platform: str
    quantity: int = Field(ge=1, le=100000)
    concurrency: int = Field(default=1, ge=1, le=64)
    time_of_day: str = Field(pattern=r"^\d{2}:\d{2}$")
    proxy_mode: str = "none"
    proxy_id: int | None = None
    proxy_group_id: int | None = None
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
    proxy_group_id: int | None = None


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
    proxy_id: int | None
    proxy_group_id: int | None
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
    proxy_group_id: int | None,
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
        email_row = resolve_required_credential("gptmail", email_credential_id)
    if spec["requires_captcha_credential"]:
        captcha_row = resolve_required_credential("yescaptcha", captcha_credential_id)

    proxy_value = None
    if spec["supports_proxy"]:
        proxy_value = resolve_proxy_selection(proxy_mode, proxy_id, proxy_group_id)

    requested_config = {
        "name": resolved_name,
        "platform": platform,
        "quantity": quantity,
        "concurrency": resolved_concurrency,
        "source": source,
        "proxy_mode": proxy_mode,
        "proxy_id": proxy_id,
        "proxy_group_id": proxy_group_id,
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
        proxy_id=proxy_id,
        proxy_group_id=proxy_group_id,
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

        if task["platform"] in {"openai-register", "openai-register-bate-L"}:
            credential = get_credential(int(task["email_credential_id"]))
            env["GPTMAIL_API_KEY"] = credential["api_key"]
            if credential["base_url"]:
                env["GPTMAIL_BASE_URL"] = credential["base_url"]
            if credential["prefix"]:
                env["GPTMAIL_PREFIX"] = credential["prefix"]
            if credential["domain"]:
                env["GPTMAIL_DOMAIN"] = credential["domain"]
            script_dir = "openai-register-bate-L" if task["platform"] == "openai-register-bate-L" else "openai-register"
            command = [
                sys.executable,
                str(ROOT_DIR / script_dir / "openai_register.py"),
                "--output-dir",
                str(task_dir / "output"),
                "--sleep-min",
                "2",
                "--sleep-max",
                "5",
            ]
            if task["proxy"]:
                command.extend(["--proxy", str(task["proxy"])])
            cwd = ROOT_DIR / script_dir
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
                proxy_mode = str(schedule["proxy_mode"] or "none")
                proxy_id = int(schedule["proxy_id"]) if schedule["proxy_id"] is not None else None
                proxy_group_id = int(schedule["proxy_group_id"]) if schedule["proxy_group_id"] is not None else None
                schedule_name = f"{schedule['name']} {today}"
                _, config = resolve_task_configuration(
                    name=schedule_name,
                    platform=str(schedule["platform"]),
                    quantity=quantity,
                    concurrency=concurrency,
                    email_credential_id=None,
                    captcha_credential_id=None,
                    proxy_mode=proxy_mode,
                    proxy_id=proxy_id,
                    proxy_group_id=proxy_group_id,
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
        if results_count >= quantity:
            status = "completed"
            error = None
        elif current_status == "stopping":
            status = "stopped"
            error = row["last_error"] or "Task stopped by operator."
        elif results_count > 0:
            status = "partial"
            error = f"Task finished with {results_count}/{quantity} successful results."
        else:
            status = "failed"
            error = row["last_error"] or "Task finished without successful results."
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
        "credentials": get_credentials(),
        "proxies": get_proxies(),
        "proxy_provider_settings": get_proxy_provider_settings(),
        "proxy_pool_items": get_proxy_pool_items(),
        "proxy_groups": get_proxy_groups(),
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
    if payload.default_gptmail_credential_id is not None and get_credential(payload.default_gptmail_credential_id)["kind"] != "gptmail":
        raise HTTPException(status_code=400, detail="Default GPTMail credential is invalid")
    if payload.default_yescaptcha_credential_id is not None and get_credential(payload.default_yescaptcha_credential_id)["kind"] != "yescaptcha":
        raise HTTPException(status_code=400, detail="Default YesCaptcha credential is invalid")
    if payload.default_proxy_id is not None:
        get_proxy(payload.default_proxy_id)
    set_setting("default_gptmail_credential_id", str(payload.default_gptmail_credential_id) if payload.default_gptmail_credential_id else None)
    set_setting("default_yescaptcha_credential_id", str(payload.default_yescaptcha_credential_id) if payload.default_yescaptcha_credential_id else None)
    set_setting("default_proxy_id", str(payload.default_proxy_id) if payload.default_proxy_id else None)
    return JSONResponse({"ok": True, "defaults": get_defaults()})


@app.post("/api/credentials")
async def create_credential(payload: CredentialCreate, request: Request) -> JSONResponse:
    require_authenticated(request)
    if payload.kind not in {"gptmail", "yescaptcha"}:
        raise HTTPException(status_code=400, detail="Unsupported credential kind")
    timestamp = now_iso()
    credential_id = execute(
        """
        INSERT INTO credentials (name, kind, api_key, base_url, prefix, domain, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.name.strip(),
            payload.kind,
            payload.api_key.strip(),
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
    proxy_id = execute(
        """
        INSERT INTO proxies (name, proxy_url, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            payload.name.strip(),
            payload.proxy_url.strip(),
            (payload.notes or "").strip() or None,
            timestamp,
            timestamp,
        ),
    )
    return JSONResponse({"ok": True, "id": proxy_id})


@app.post("/api/proxy-providers")
async def save_proxy_provider(payload: ProxyProviderSettingsPayload, request: Request) -> JSONResponse:
    require_authenticated(request)
    save_proxy_provider_settings(payload)
    return JSONResponse({"ok": True})


@app.post("/api/proxy-pool/sync")
async def sync_proxy_pool(payload: ProxyPoolSyncPayload, request: Request) -> JSONResponse:
    require_authenticated(request)
    imported = sync_proxy_provider(payload.provider_key)
    return JSONResponse({"ok": True, "imported": imported})


@app.post("/api/proxy-groups")
async def create_proxy_group(payload: ProxyGroupCreate, request: Request) -> JSONResponse:
    require_authenticated(request)
    timestamp = now_iso()
    group_id = execute(
        "INSERT INTO proxy_groups (name, notes, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (payload.name.strip(), (payload.notes or "").strip() or None, timestamp, timestamp),
    )
    add_group_members(
        group_id=group_id,
        proxy_urls=payload.proxy_urls,
        proxy_ids=payload.proxy_ids,
        pool_item_ids=payload.pool_item_ids,
    )
    return JSONResponse({"ok": True, "id": group_id})


@app.post("/api/proxy-groups/assign")
async def assign_proxy_group_members(payload: ProxyGroupAssignPayload, request: Request) -> JSONResponse:
    require_authenticated(request)
    get_proxy_group(payload.group_id)
    add_group_members(
        group_id=payload.group_id,
        proxy_urls=payload.proxy_urls,
        proxy_ids=payload.proxy_ids,
        pool_item_ids=payload.pool_item_ids,
    )
    execute_no_return("UPDATE proxy_groups SET updated_at = ? WHERE id = ?", (now_iso(), payload.group_id))
    return JSONResponse({"ok": True})


@app.delete("/api/proxy-groups/{group_id}")
async def delete_proxy_group(group_id: int, request: Request) -> JSONResponse:
    require_authenticated(request)
    get_proxy_group(group_id)
    active = fetch_one(
        "SELECT id FROM tasks WHERE requested_config_json LIKE ? AND status IN ('queued', 'running', 'stopping')",
        (f'%"proxy_group_id": {group_id}%',),
    )
    if active is not None:
        raise HTTPException(status_code=409, detail="Proxy group is used by an active task")
    execute_no_return("DELETE FROM proxy_group_members WHERE group_id = ?", (group_id,))
    execute_no_return("DELETE FROM proxy_group_states WHERE group_id = ?", (group_id,))
    execute_no_return("DELETE FROM proxy_groups WHERE id = ?", (group_id,))
    return JSONResponse({"ok": True})


@app.delete("/api/proxy-groups/{group_id}/members/{member_id}")
async def delete_proxy_group_member(group_id: int, member_id: int, request: Request) -> JSONResponse:
    require_authenticated(request)
    get_proxy_group(group_id)
    get_proxy_group_member(group_id, member_id)
    execute_no_return("DELETE FROM proxy_group_members WHERE group_id = ? AND id = ?", (group_id, member_id))
    execute_no_return("UPDATE proxy_groups SET updated_at = ? WHERE id = ?", (now_iso(), group_id))
    return JSONResponse({"ok": True})


@app.post("/api/proxy-groups/{group_id}/reorder")
async def reorder_proxy_group(group_id: int, payload: ProxyGroupMemberOrderPayload, request: Request) -> JSONResponse:
    require_authenticated(request)
    get_proxy_group(group_id)
    reorder_proxy_group_members(group_id, payload.member_ids)
    return JSONResponse({"ok": True})


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
        proxy_group_id=payload.proxy_group_id,
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
    resolve_proxy_selection(payload.proxy_mode, payload.proxy_id, payload.proxy_group_id) if PLATFORMS[payload.platform]["supports_proxy"] else None
    timestamp = now_iso()
    schedule_id = execute(
        """
        INSERT INTO schedules (name, platform, quantity, concurrency, time_of_day, proxy_mode, proxy_id, proxy_group_id, enabled, last_run_date, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
        """,
        (
            payload.name.strip(),
            payload.platform,
            payload.quantity,
            payload.concurrency,
            payload.time_of_day,
            payload.proxy_mode,
            payload.proxy_id,
            payload.proxy_group_id,
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
        proxy_group_id=None,
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
