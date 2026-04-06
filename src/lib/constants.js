export const APP_NAME = "MREGISTER";

export const PLATFORM_SPECS = {
  "chatgpt-register-lib": {
    label: "ChatGPT Register Lib",
    default_concurrency: 1,
    notes: "使用 Python lib 驱动执行注册，并通过 OutlookManager 接口统一取号和收码。",
  },
};

export const TASK_STATUSES = [
  "queued",
  "running",
  "completed",
  "partial",
  "failed",
  "stopped",
  "interrupted",
];

export const NAV_ITEMS = [
  ["dashboard", "总览"],
  ["credentials", "凭据"],
  ["create-task", "新建任务"],
  ["task-detail", "任务详情"],
  ["api-keys", "API 接口"],
  ["docs", "安装文档"],
];

export const AGREEMENT_CONFIRM_TEXT = "我同意此条款";
