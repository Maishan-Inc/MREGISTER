import React, { useEffect, useRef, useState } from 'react';
import {
  APP_CONFIG,
  NAV_ITEMS,
  TASK_STATUSES,
  api,
  getPlatformKeys,
  getTaskDisplayName,
  initialTaskDraft,
  isEmailCredentialKind,
  isMobileLayout,
  normalizeTaskDraft,
  parseIntOrNull,
  SIDEBAR_STORAGE_KEY,
  statusLabel,
  tr,
} from './config.js';
import { BusyButton, Modal } from './ui.jsx';

const SIDEBAR_LOGO_SRC = '/static/MAISHANhlogomini.png';
const DOCS_LOG_IMAGE_SRC = '/static/docs-log-preview.jpg';
const PROJECT_GITHUB_URL = 'https://github.com/Maishan-Inc/MREGISTER';
const SECTION_TITLE_KEYS = {
  dashboard: 'section_overview',
  credentials: 'section_credentials',
  proxies: 'section_proxies',
  'create-task': 'section_tasks',
  'task-detail': 'section_task_detail',
  schedules: 'section_schedules',
  cpamc: 'cpamc_title',
  'api-keys': 'section_api',
  docs: 'section_docs',
};

function normalizeStatePayload(payload) {
  return {
    ...payload,
    credentials: payload.credentials || [],
    proxies: payload.proxies || [],
    tasks: payload.tasks || [],
    schedules: payload.schedules || [],
    apiKeys: payload.apiKeys || payload.api_keys || [],
    defaults: payload.defaults || {},
    cpamc: payload.cpamc || {},
    dashboard: payload.dashboard || {},
    platforms: payload.platforms || {},
  };
}

function credentialKindLabel(kind) {
  const keyMap = {
    gptmail: 'credential_kind_gptmail',
    moemail: 'credential_kind_moemail',
    cloudflare_temp_email: 'credential_kind_cloudflare_temp_email',
    yescaptcha: 'credential_kind_yescaptcha',
  };
  return tr(keyMap[kind] || kind);
}

function getCredentialFieldMeta(kind) {
  const isEmail = isEmailCredentialKind(kind);
  return {
    isEmail,
    showSecret: kind === 'cloudflare_temp_email',
    apiKeyLabel: tr({
      gptmail: 'credential_api_key_label_gptmail',
      moemail: 'credential_api_key_label_moemail',
      cloudflare_temp_email: 'credential_api_key_label_cloudflare_temp_email',
      yescaptcha: 'credential_api_key_label_yescaptcha',
    }[kind] || 'field_api_key'),
    hint: kind === 'gptmail'
      ? tr('gptmail_optional_hint')
      : kind === 'moemail'
        ? tr('moemail_optional_hint')
        : kind === 'cloudflare_temp_email'
          ? tr('cloudflare_optional_hint')
          : '',
    secretLabel: kind === 'cloudflare_temp_email' ? tr('credential_secret_label_cloudflare_temp_email') : tr('field_secret'),
    secretPlaceholder: kind === 'cloudflare_temp_email'
      ? tr('credential_secret_placeholder_cloudflare_temp_email')
      : tr('field_secret_placeholder'),
  };
}

function SidebarIcon({ name }) {
  switch (name) {
    case 'dashboard':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M4 13.5h7V20H4zM13 4h7v9H13zM13 15h7v5H13zM4 4h7v7.5H4z" />
        </svg>
      );
    case 'credentials':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M12 3a5 5 0 0 0-1.2 9.86A7.51 7.51 0 0 0 4 20h2a5.5 5.5 0 0 1 11 0h3a4 4 0 0 0-4-4h-1.2a5 5 0 0 0-2.8-13Z" />
        </svg>
      );
    case 'proxies':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M4 7h16v4H4zM6 13h12v4H6zM8 3h8v2H8zM10 18h4v3h-4z" />
        </svg>
      );
    case 'create-task':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M5 4h9l5 5v11H5zM14 4v5h5M12 11v6M9 14h6" />
        </svg>
      );
    case 'task-detail':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M6 4h12v16H6zM9 8h6M9 12h6M9 16h4" />
        </svg>
      );
    case 'schedules':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M7 2v3M17 2v3M4 7h16v13H4zM8 11h3v3H8zM13 11h3v3h-3zM8 16h3v1H8zM13 16h3v1h-3z" />
        </svg>
      );
    case 'cpamc':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M5 7h14M5 12h14M5 17h14M8 4v16M16 4v16" />
        </svg>
      );
    case 'api-keys':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M14 7a4 4 0 1 1 3.87 5H16l-2 2h-2l-1 1H8l-2 2H3v-3l6.17-6.17A4 4 0 0 1 14 7Zm3-1.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3Z" />
        </svg>
      );
    case 'docs':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M6 4h9l3 3v13H6zM15 4v4h4M9 11h6M9 15h6" />
        </svg>
      );
    case 'logout':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M10 4H5v16h5M14 8l4 4-4 4M18 12H9" />
        </svg>
      );
    default:
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="6" />
        </svg>
      );
  }
}

function GithubIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 2C6.48 2 2 6.58 2 12.23c0 4.52 2.87 8.35 6.84 9.7.5.1.68-.22.68-.5 0-.24-.01-1.05-.01-1.9-2.78.62-3.36-1.21-3.36-1.21-.45-1.18-1.11-1.5-1.11-1.5-.91-.64.07-.63.07-.63 1 .08 1.53 1.06 1.53 1.06.9 1.57 2.35 1.12 2.92.85.09-.67.35-1.12.63-1.38-2.22-.26-4.56-1.14-4.56-5.09 0-1.13.39-2.05 1.03-2.78-.1-.26-.45-1.31.1-2.73 0 0 .84-.28 2.75 1.06A9.3 9.3 0 0 1 12 6.84c.85 0 1.71.12 2.51.35 1.9-1.34 2.74-1.06 2.74-1.06.55 1.42.21 2.47.1 2.73.64.73 1.03 1.65 1.03 2.78 0 3.96-2.34 4.82-4.57 5.08.36.32.68.96.68 1.94 0 1.4-.01 2.53-.01 2.88 0 .28.18.61.69.5A10.25 10.25 0 0 0 22 12.23C22 6.58 17.52 2 12 2Z" />
    </svg>
  );
}

function getDocsContent(uiLang, apiBaseUrl) {
  const isZh = String(uiLang || '').toLowerCase().startsWith('zh');

  if (isZh) {
    return {
      heroTitle: '部署、初始化与使用流程',
      heroText: '这一页把 MREGISTER 的部署、首次配置、日常任务操作和 API 接入整理成一条完整链路。按顺序执行即可，不需要在多个页面之间来回查找。',
      deployTitle: '一键部署',
      deployText: '推荐直接使用 Docker Compose。本仓库当前会基于本地代码构建镜像，适合你同步前端和后端改动后立即部署。',
      deploySteps: [
        '确认服务器已安装 Docker 与 Docker Compose。',
        '在项目根目录执行 `docker compose up -d --build`。',
        '执行 `docker compose ps` 确认容器状态为 `Up`。',
        '执行 `docker compose logs -f` 查看启动日志和错误输出。',
        `浏览器打开 ${apiBaseUrl || 'http://127.0.0.1:8000'} 进入控制台。`,
      ],
      localTitle: '本地调试',
      localText: '如果你正在开发界面或调试后端逻辑，可以先使用 Python 直接启动服务。',
      localCommands: [
        'python -m pip install -r web_console/requirements.txt',
        'uvicorn web_console.app:app --host 0.0.0.0 --port 8000',
      ],
      firstUseTitle: '首次初始化',
      firstUseText: '部署完成后，首次打开页面会先进入协议确认和管理员密码初始化流程。完成后再配置默认资源。',
      firstUseSteps: [
        '阅读并确认 Maishan Inc. 非商业性协议。',
        '设置管理员密码并进入后台。',
        '在“凭据”页面添加邮件凭据（GPTMail、MoeMail 或 Cloudflare Temp Email）。',
        '如需使用 grok-register，再添加 YesCaptcha 凭据。',
        '如需固定出口，在“代理”页面添加代理并设置默认值。',
        '在“API”页面创建 API Key，供外部程序调用。',
      ],
      usageTitle: '日常使用流程',
      usageText: '如果你主要在后台手动操作，建议按下面的顺序使用。',
      usageSteps: [
        '在“新建任务”中选择驱动、数量、并发和代理模式。',
        '创建任务后跳转到“任务详情”，查看实时日志和完成数。',
        '任务结束后下载压缩包并核对结果。',
        '如果是高频固定需求，用“定时任务”自动触发。',
      ],
      apiTitle: 'API 接入流程',
      apiText: '如果你要把项目接入自己的程序，推荐只调用外部 API，不要直接操作数据库。',
      apiSteps: [
        '在后台先创建一个 API Key。',
        '调用 `POST /api/external/tasks` 创建任务。',
        '轮询 `GET /api/external/tasks/{task_id}` 查看进度。',
        '任务完成后调用 `GET /api/external/tasks/{task_id}/download` 下载结果。',
      ],
      endpointTitle: '接口速查',
      endpointHeaders: ['方法', '路径', '说明'],
      endpoints: [
        ['POST', '/api/external/tasks', '创建一个新的外部任务'],
        ['GET', '/api/external/tasks/{task_id}', '查询任务状态、完成数量和下载地址'],
        ['GET', '/api/external/tasks/{task_id}/download', '下载任务结果压缩包'],
      ],
      paramsTitle: '创建任务参数',
      paramHeaders: ['字段', '类型', '必填', '说明'],
      params: [
        ['platform', 'string', '是', '支持 `chatgpt-register-v2` 与 `grok-register`'],
        ['quantity', 'integer', '是', '目标成功数量，按真实成功数统计'],
        ['use_proxy', 'boolean', '否', '是否使用后台默认代理'],
        ['concurrency', 'integer', '否', '并发数，默认 1'],
        ['name', 'string', '否', '自定义任务名称'],
      ],
      tipsTitle: '部署建议',
      tips: [
        '持久化目录是 `web_console/runtime/`，请定期备份。',
        '生产环境建议在外层加 Nginx 或 Caddy，并启用 HTTPS。',
        '不要把后台直接裸露到公网上。',
        '更新代码后优先执行 `docker compose up -d --build`。',
      ],
      createExampleTitle: '创建任务示例',
      createExampleHttp: `POST ${apiBaseUrl}/api/external/tasks
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "platform": "chatgpt-register-v2",
  "quantity": 10,
  "use_proxy": true,
  "concurrency": 1
}`,
      createExampleCurl: `curl -X POST "${apiBaseUrl}/api/external/tasks" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d "{\\"platform\\":\\"chatgpt-register-v2\\",\\"quantity\\":10,\\"use_proxy\\":true,\\"concurrency\\":1}"`,
      queryExampleTitle: '查询任务示例',
      queryExampleHttp: `GET ${apiBaseUrl}/api/external/tasks/TASK_ID
Authorization: Bearer YOUR_API_KEY`,
      queryExampleCurl: `curl "${apiBaseUrl}/api/external/tasks/TASK_ID" \\
  -H "Authorization: Bearer YOUR_API_KEY"`,
      downloadExampleTitle: '下载结果示例',
      downloadExampleCurl: `curl -L "${apiBaseUrl}/api/external/tasks/TASK_ID/download" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -o result.zip`,
    };
  }

  return {
    heroTitle: 'Deployment, Setup, and Usage Flow',
    heroText: 'This page condenses the full MREGISTER flow into one place: deploy, initialize, operate tasks, and integrate via API.',
    deployTitle: 'Recommended Deployment',
    deployText: 'Use Docker Compose by default. The repository now builds from the local source tree, so frontend and backend changes are included immediately.',
    deploySteps: [
      'Install Docker and Docker Compose on the host.',
      'Run `docker compose up -d --build` from the project root.',
      'Run `docker compose ps` to verify the container is up.',
      'Run `docker compose logs -f` to inspect boot logs and runtime errors.',
      `Open ${apiBaseUrl || 'http://127.0.0.1:8000'} in your browser.`,
    ],
    localTitle: 'Local Development',
    localText: 'If you are debugging the UI or backend directly, start the app with Python.',
    localCommands: [
      'python -m pip install -r web_console/requirements.txt',
      'uvicorn web_console.app:app --host 0.0.0.0 --port 8000',
    ],
    firstUseTitle: 'First-Time Initialization',
    firstUseText: 'On first visit, the console is locked until the agreement flow and admin password setup are completed.',
    firstUseSteps: [
      'Read and accept the Maishan Inc. non-commercial agreement.',
      'Set the admin password.',
        'Add an email credential (GPTMail, MoeMail, or Cloudflare Temp Email).',
      'Add a YesCaptcha credential if you plan to use grok-register.',
      'Add and optionally set a default proxy.',
      'Create an API key for external integrations.',
    ],
    usageTitle: 'Daily Workflow',
    usageText: 'For manual operation inside the console, the following order keeps things simple.',
    usageSteps: [
      'Create a task with driver, quantity, concurrency, and proxy mode.',
      'Open Task Detail to inspect live logs and completion counts.',
      'Download the archive after completion and verify outputs.',
      'Use schedules for repeated daily jobs.',
    ],
    apiTitle: 'API Workflow',
    apiText: 'For external integrations, use the public API only. Do not bypass the console by writing directly to the database.',
    apiSteps: [
      'Create an API key in the console.',
      'Call `POST /api/external/tasks` to create a task.',
      'Poll `GET /api/external/tasks/{task_id}` for progress.',
      'Call `GET /api/external/tasks/{task_id}/download` when the task is complete.',
    ],
    endpointTitle: 'Endpoint Quick Reference',
    endpointHeaders: ['Method', 'Path', 'Description'],
    endpoints: [
      ['POST', '/api/external/tasks', 'Create a new external task'],
      ['GET', '/api/external/tasks/{task_id}', 'Query task status, completion count, and download URL'],
      ['GET', '/api/external/tasks/{task_id}/download', 'Download the task result archive'],
    ],
    paramsTitle: 'Create Task Parameters',
    paramHeaders: ['Field', 'Type', 'Required', 'Description'],
    params: [
      ['platform', 'string', 'yes', 'Supports `chatgpt-register-v2` and `grok-register`'],
      ['quantity', 'integer', 'yes', 'Target success count'],
      ['use_proxy', 'boolean', 'no', 'Whether to use the configured default proxy'],
      ['concurrency', 'integer', 'no', 'Concurrency, default is 1'],
      ['name', 'string', 'no', 'Custom task name'],
    ],
    tipsTitle: 'Operational Notes',
    tips: [
      'Persist and back up `web_console/runtime/` regularly.',
      'Use a reverse proxy and HTTPS in production.',
      'Do not expose the console directly on the public internet.',
      'After code changes, prefer `docker compose up -d --build`.',
    ],
    createExampleTitle: 'Create Task Example',
    createExampleHttp: `POST ${apiBaseUrl}/api/external/tasks
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "platform": "chatgpt-register-v2",
  "quantity": 10,
  "use_proxy": true,
  "concurrency": 1
}`,
    createExampleCurl: `curl -X POST "${apiBaseUrl}/api/external/tasks" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d "{\\"platform\\":\\"chatgpt-register-v2\\",\\"quantity\\":10,\\"use_proxy\\":true,\\"concurrency\\":1}"`,
    queryExampleTitle: 'Query Task Example',
    queryExampleHttp: `GET ${apiBaseUrl}/api/external/tasks/TASK_ID
Authorization: Bearer YOUR_API_KEY`,
    queryExampleCurl: `curl "${apiBaseUrl}/api/external/tasks/TASK_ID" \\
  -H "Authorization: Bearer YOUR_API_KEY"`,
    downloadExampleTitle: 'Download Result Example',
    downloadExampleCurl: `curl -L "${apiBaseUrl}/api/external/tasks/TASK_ID/download" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -o result.zip`,
  };
}

export function ConsoleApp() {
  const [activeSection, setActiveSection] = useState('dashboard');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === '1');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [busyKeys, setBusyKeys] = useState({});
  const [loadError, setLoadError] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [flashNotice, setFlashNotice] = useState(null);
  const [taskListMode, setTaskListMode] = useState('task');
  const [taskFilterStatus, setTaskFilterStatus] = useState('all');
  const [selectedTaskId, setSelectedTaskId] = useState(null);
  const [selectedScheduleId, setSelectedScheduleId] = useState(null);
  const [flashKey, setFlashKey] = useState('');
  const [modalState, setModalState] = useState(null);
  const [statePayload, setStatePayload] = useState({
    credentials: [],
    proxies: [],
    tasks: [],
    schedules: [],
    apiKeys: [],
    defaults: {},
    cpamc: {},
    dashboard: {},
    platforms: APP_CONFIG.platforms || {},
  });
  const [defaultsDraft, setDefaultsDraft] = useState({
    default_gptmail_credential_id: '',
    default_yescaptcha_credential_id: '',
    default_proxy_id: '',
  });
  const [credentialDraft, setCredentialDraft] = useState({
    name: '',
    kind: 'gptmail',
    api_key: '',
    secret: '',
    base_url: '',
    prefix: '',
    domain: '',
    notes: '',
  });
  const [proxyDraft, setProxyDraft] = useState({
    name: '',
    proxy_url: '',
    notes: '',
  });
  const [taskDraft, setTaskDraft] = useState(initialTaskDraft(APP_CONFIG.platforms || {}));
  const [scheduleDraft, setScheduleDraft] = useState({
    name: '',
    platform: getPlatformKeys(APP_CONFIG.platforms || {})[0] || 'chatgpt-register-v2',
    quantity: '1',
    concurrency: '1',
    time_of_day: '',
    use_proxy: false,
    auto_import_cpamc: false,
  });
  const [cpamcDraft, setCpamcDraft] = useState({
    enabled: false,
    base_url: '',
    management_key: '',
    linked: false,
    last_error: '',
    auto_import_enabled: false,
  });
  const [cpamcDirty, setCpamcDirty] = useState(false);
  const [apiKeyName, setApiKeyName] = useState('');
  const modalResolverRef = useRef(null);
  const consoleRef = useRef(null);

  const mailCredentials = statePayload.credentials.filter((item) => isEmailCredentialKind(item.kind));
  const captchaCredentials = statePayload.credentials.filter((item) => item.kind === 'yescaptcha');
  const normalTasks = statePayload.tasks.filter((task) => task.source !== 'schedule');
  const filteredTasks = taskFilterStatus === 'all'
    ? normalTasks
    : normalTasks.filter((task) => task.status === taskFilterStatus);
  const visibleTask = filteredTasks.find((item) => item.id === selectedTaskId) || filteredTasks[0] || null;
  const visibleSchedule = statePayload.schedules.find((item) => item.id === selectedScheduleId) || statePayload.schedules[0] || null;
  const currentPlatformSpec = statePayload.platforms[taskDraft.platform] || {};
  const credentialFieldMeta = getCredentialFieldMeta(credentialDraft.kind);
  const currentSectionLabel = tr(SECTION_TITLE_KEYS[activeSection] || 'section_overview');
  const topbarBreadcrumbs = [
    tr('topbar_workspace'),
    ...(activeSection === 'dashboard' ? [] : [currentSectionLabel]),
    ...(activeSection === 'task-detail' && taskListMode === 'task' && visibleTask ? [getTaskDisplayName(visibleTask)] : []),
    ...(activeSection === 'task-detail' && taskListMode === 'schedule' && visibleSchedule ? [`${visibleSchedule.name} ${tr('schedule_tag_suffix')}`] : []),
  ];
  const logoutLabel = tr('nav_logout');

  useEffect(() => {
    const onResize = () => {
      if (!isMobileLayout()) {
        setSidebarOpen(false);
      }
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    if (!isMobileLayout()) {
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, sidebarCollapsed ? '1' : '0');
    }
  }, [sidebarCollapsed]);

  useEffect(() => {
    if (visibleTask) {
      setSelectedTaskId(visibleTask.id);
    }
  }, [visibleTask?.id]);

  useEffect(() => {
    if (consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
    }
  }, [visibleTask?.id, visibleTask?.console_tail]);

  useEffect(() => {
    if (!flashNotice) {
      return undefined;
    }
    const timer = window.setTimeout(() => setFlashNotice(null), 3200);
    return () => window.clearTimeout(timer);
  }, [flashNotice]);

  useEffect(() => {
    refreshState({ initial: true }).catch((error) => {
      setLoadError(error.message);
      setLoaded(true);
    });

    const timer = window.setInterval(() => {
      refreshState().catch(() => {});
    }, 4000);
    return () => window.clearInterval(timer);
  }, []);

  async function refreshState({ initial = false } = {}) {
    const payload = normalizeStatePayload(await api('/api/state'));
    setStatePayload(payload);
    setLoaded(true);
    setLoadError('');
    setDefaultsDraft({
      default_gptmail_credential_id: payload.defaults.default_gptmail_credential_id ? String(payload.defaults.default_gptmail_credential_id) : '',
      default_yescaptcha_credential_id: payload.defaults.default_yescaptcha_credential_id ? String(payload.defaults.default_yescaptcha_credential_id) : '',
      default_proxy_id: payload.defaults.default_proxy_id ? String(payload.defaults.default_proxy_id) : '',
    });
    if (initial || !cpamcDirty) {
      setCpamcDraft({
        enabled: Boolean(payload.cpamc?.enabled),
        base_url: payload.cpamc?.base_url || '',
        management_key: payload.cpamc?.management_key || '',
        linked: Boolean(payload.cpamc?.linked),
        last_error: payload.cpamc?.last_error || '',
        auto_import_enabled: Boolean(payload.cpamc?.auto_import_enabled),
      });
    }
    setTaskDraft((current) => normalizeTaskDraft(initial ? initialTaskDraft(payload.platforms) : current, payload.platforms, payload.credentials, payload.proxies));
    setScheduleDraft((current) => {
      const platform = payload.platforms[current.platform] ? current.platform : (getPlatformKeys(payload.platforms)[0] || 'chatgpt-register-v2');
      return { ...current, platform };
    });
    setSelectedTaskId((current) => {
      if (payload.tasks.some((item) => item.id === current)) {
        return current;
      }
      return payload.tasks[0]?.id || null;
    });
    setSelectedScheduleId((current) => {
      if (payload.schedules.some((item) => item.id === current)) {
        return current;
      }
      return payload.schedules[0]?.id || null;
    });
  }

  async function withBusy(key, action) {
    setBusyKeys((current) => ({ ...current, [key]: true }));
    try {
      return await action();
    } finally {
      setBusyKeys((current) => {
        const next = { ...current };
        delete next[key];
        return next;
      });
    }
  }

  function isBusy(key) {
    return Boolean(busyKeys[key]);
  }

  function closeModal(result) {
    const resolver = modalResolverRef.current;
    modalResolverRef.current = null;
    setModalState(null);
    if (resolver) {
      resolver(result);
    }
  }

  function openModal(options) {
    return new Promise((resolve) => {
      modalResolverRef.current = resolve;
      setModalState(options);
    });
  }

  async function confirmAction(options) {
    return openModal({
      title: options.title,
      message: options.message,
      confirmLabel: options.confirmLabel || tr('delete'),
      cancelLabel: options.cancelLabel || tr('created_task_modal_cancel'),
    });
  }

  function switchSection(sectionId) {
    setActiveSection(sectionId);
    if (isMobileLayout()) {
      setSidebarOpen(false);
    }
  }

  async function handleDefaultsSubmit(event) {
    event.preventDefault();
    await withBusy('defaults-save', async () => {
      await api('/api/defaults', {
        method: 'POST',
        body: JSON.stringify({
          default_gptmail_credential_id: parseIntOrNull(defaultsDraft.default_gptmail_credential_id),
          default_yescaptcha_credential_id: parseIntOrNull(defaultsDraft.default_yescaptcha_credential_id),
          default_proxy_id: parseIntOrNull(defaultsDraft.default_proxy_id),
        }),
      });
      await refreshState();
    });
  }

  async function handleCredentialSubmit(event) {
    event.preventDefault();
    await withBusy('credential-save', async () => {
      await api('/api/credentials', {
        method: 'POST',
        body: JSON.stringify({
          ...credentialDraft,
          secret: credentialDraft.kind === 'cloudflare_temp_email' ? credentialDraft.secret || null : null,
          base_url: isEmailCredentialKind(credentialDraft.kind) ? credentialDraft.base_url || null : null,
          prefix: isEmailCredentialKind(credentialDraft.kind) ? credentialDraft.prefix || null : null,
          domain: isEmailCredentialKind(credentialDraft.kind) ? credentialDraft.domain || null : null,
          notes: credentialDraft.notes || null,
        }),
      });
      setCredentialDraft({
        name: '',
        kind: 'gptmail',
        api_key: '',
        secret: '',
        base_url: '',
        prefix: '',
        domain: '',
        notes: '',
      });
      await refreshState();
    });
  }

  async function handleProxySubmit(event) {
    event.preventDefault();
    await withBusy('proxy-save', async () => {
      await api('/api/proxies', {
        method: 'POST',
        body: JSON.stringify({
          ...proxyDraft,
          notes: proxyDraft.notes || null,
        }),
      });
      setProxyDraft({ name: '', proxy_url: '', notes: '' });
      await refreshState();
    });
  }

  async function handleTaskSubmit(event) {
    event.preventDefault();
    await withBusy('task-save', async () => {
      const result = await api('/api/tasks', {
        method: 'POST',
        body: JSON.stringify({
          ...taskDraft,
          quantity: Number(taskDraft.quantity),
          concurrency: Number(taskDraft.concurrency || 1),
          email_credential_id: parseIntOrNull(taskDraft.email_credential_id),
          captcha_credential_id: parseIntOrNull(taskDraft.captcha_credential_id),
          proxy_id: taskDraft.proxy_mode === 'custom' ? parseIntOrNull(taskDraft.proxy_id) : null,
        }),
      });
      await refreshState();
      const shouldOpenTask = await openModal({
        title: tr('created_task_modal_title'),
        message: tr('created_task_confirm', { id: result.id }),
        confirmLabel: tr('created_task_modal_confirm'),
        cancelLabel: tr('created_task_modal_cancel'),
      });
      if (shouldOpenTask) {
        setSelectedTaskId(Number(result.id));
        setActiveSection('task-detail');
      }
    });
  }

  async function handleScheduleSubmit(event) {
    event.preventDefault();
    await withBusy('schedule-save', async () => {
      await api('/api/schedules', {
        method: 'POST',
        body: JSON.stringify({
          ...scheduleDraft,
          quantity: Number(scheduleDraft.quantity),
          concurrency: Number(scheduleDraft.concurrency || 1),
          enabled: true,
        }),
      });
      setScheduleDraft({
        name: '',
        platform: getPlatformKeys(statePayload.platforms)[0] || 'chatgpt-register-v2',
        quantity: '1',
        concurrency: '1',
        time_of_day: '',
        use_proxy: false,
        auto_import_cpamc: false,
      });
      await refreshState();
    });
  }

  async function handleCpamcSave(event) {
    event.preventDefault();
    await withBusy('cpamc-save', async () => {
      try {
        await api('/api/cpamc', {
          method: 'POST',
          body: JSON.stringify({
            enabled: cpamcDraft.enabled,
            base_url: cpamcDraft.base_url,
            management_key: cpamcDraft.management_key,
            auto_import_enabled: cpamcDraft.auto_import_enabled,
          }),
        });
        setCpamcDirty(false);
        await refreshState();
      } catch (error) {
        setLoadError(error.message);
      }
    });
  }

  async function handleCpamcTest() {
    await withBusy('cpamc-test', async () => {
      try {
        await api('/api/cpamc/test', {
          method: 'POST',
          body: JSON.stringify({
            enabled: cpamcDraft.enabled,
            base_url: cpamcDraft.base_url,
            management_key: cpamcDraft.management_key,
            auto_import_enabled: cpamcDraft.auto_import_enabled,
          }),
        });
        setCpamcDirty(false);
        await refreshState();
      } catch (error) {
        setLoadError(error.message);
        setCpamcDraft((current) => ({
          ...current,
          linked: false,
          last_error: error.message,
        }));
      }
    });
  }

  async function handleApiKeySubmit(event) {
    event.preventDefault();
    await withBusy('api-key-save', async () => {
      const result = await api('/api/api-keys', {
        method: 'POST',
        body: JSON.stringify({ name: apiKeyName }),
      });
      setApiKeyName('');
      setFlashKey(result.api_key);
      await refreshState();
    });
  }

  async function handleLogout() {
    await withBusy('logout', async () => {
      await api('/api/auth/logout', { method: 'POST' });
      window.location.reload();
    });
  }

  async function handleSetDefault(kind, id) {
    await withBusy(`set-default-${kind}-${id}`, async () => {
      await api('/api/defaults', {
        method: 'POST',
        body: JSON.stringify({
          default_gptmail_credential_id: kind === 'default_gptmail_credential_id'
            ? id
            : (statePayload.defaults.default_gptmail_credential_id || null),
          default_yescaptcha_credential_id: kind === 'default_yescaptcha_credential_id'
            ? id
            : (statePayload.defaults.default_yescaptcha_credential_id || null),
          default_proxy_id: kind === 'default_proxy_id'
            ? id
            : (statePayload.defaults.default_proxy_id || null),
        }),
      });
      await refreshState();
    });
  }

  async function handleDeleteCredential(item) {
    if (!await confirmAction({
      title: tr('delete'),
      message: tr('delete_credential_confirm', { name: item.name }),
      confirmLabel: tr('delete'),
    })) {
      return;
    }
    await withBusy(`credential-delete-${item.id}`, async () => {
      await api(`/api/credentials/${item.id}`, { method: 'DELETE' });
      await refreshState();
    });
  }

  async function handleDeleteProxy(item) {
    if (!await confirmAction({
      title: tr('delete'),
      message: tr('delete_proxy_confirm', { name: item.name }),
      confirmLabel: tr('delete'),
    })) {
      return;
    }
    await withBusy(`proxy-delete-${item.id}`, async () => {
      await api(`/api/proxies/${item.id}`, { method: 'DELETE' });
      await refreshState();
    });
  }

  async function handleStopTask(task) {
    await withBusy(`task-stop-${task.id}`, async () => {
      await api(`/api/tasks/${task.id}/stop`, { method: 'POST' });
      await refreshState();
    });
  }

  async function handleDeleteTask(task) {
    if (!await confirmAction({
      title: tr('delete_task'),
      message: tr('delete_task_confirm', { id: task.id }),
      confirmLabel: tr('delete_task'),
    })) {
      return;
    }
    await withBusy(`task-delete-${task.id}`, async () => {
      await api(`/api/tasks/${task.id}`, { method: 'DELETE' });
      setSelectedTaskId(null);
      await refreshState();
    });
  }

  async function handleImportTaskToCpamc(task) {
    await withBusy(`cpamc-import-${task.id}`, async () => {
      try {
        const result = await api(`/api/tasks/${task.id}/cpamc-import`, { method: 'POST' });
        await refreshState();
        await openModal({
          title: tr('cpamc_import_result_title'),
          message: result.failed_count
            ? tr('cpamc_import_partial', { success: result.imported_count, failed: result.failed_count })
            : tr('cpamc_import_success', { count: result.imported_count }),
          confirmLabel: tr('modal_close'),
        });
      } catch (error) {
        setLoadError(error.message);
      }
    });
  }

  function getTodayDateKey() {
    const value = new Date();
    const year = String(value.getFullYear());
    const month = String(value.getMonth() + 1).padStart(2, '0');
    const day = String(value.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  function getScheduleTaskSummary(task) {
    if (!task || task.source !== 'schedule' || !task.schedule_id) {
      return null;
    }
    const scheduleId = Number(task.schedule_id);
    const schedule = statePayload.schedules.find((item) => Number(item.id) === scheduleId);
    if (!schedule) {
      return null;
    }
    const relatedTasks = statePayload.tasks.filter((item) => Number(item.schedule_id) === scheduleId);
    const todayTask = relatedTasks.find((item) => String(item.created_at || '').startsWith(getTodayDateKey())) || null;
    return {
      schedule,
      completedRuns: relatedTasks.filter((item) => item.status === 'completed').length,
      todayTask,
    };
  }

  function getScheduleDetail(schedule) {
    if (!schedule) {
      return null;
    }
    const relatedTasks = statePayload.tasks.filter((item) => Number(item.schedule_id) === Number(schedule.id));
    const todayTask = relatedTasks.find((item) => String(item.created_at || '').startsWith(getTodayDateKey())) || null;
    const latestTask = relatedTasks[0] || null;
    const importTask = relatedTasks.find((item) => Number(item.cpamc_importable_count || 0) > 0) || null;
    return {
      relatedTasks,
      todayTask,
      latestTask,
      importTask,
      completedRuns: relatedTasks.filter((item) => item.status === 'completed').length,
    };
  }

  async function handleToggleSchedule(item) {
    await withBusy(`schedule-toggle-${item.id}`, async () => {
      await api(`/api/schedules/${item.id}/toggle`, { method: 'POST' });
      await refreshState();
    });
  }

  async function handleRunScheduleNow(item) {
    await withBusy(`schedule-run-${item.id}`, async () => {
      const result = await api(`/api/schedules/${item.id}/run`, { method: 'POST' });
      setSelectedTaskId(Number(result.id));
      await refreshState();
    });
  }

  async function handleDeleteSchedule(item) {
    if (!await confirmAction({
      title: tr('delete'),
      message: tr('delete_schedule_confirm'),
      confirmLabel: tr('delete'),
    })) {
      return;
    }
    await withBusy(`schedule-delete-${item.id}`, async () => {
      await api(`/api/schedules/${item.id}`, { method: 'DELETE' });
      await refreshState();
    });
  }

  async function handleDeleteApiKey(item) {
    if (!await confirmAction({
      title: tr('delete'),
      message: tr('delete_api_key_confirm'),
      confirmLabel: tr('delete'),
    })) {
      return;
    }
    await withBusy(`api-key-delete-${item.id}`, async () => {
      await api(`/api/api-keys/${item.id}`, { method: 'DELETE' });
      await refreshState();
    });
  }

  function renderDashboard() {
    const metrics = statePayload.dashboard || {};
    return (
      <section className="section-card active">
        <div className="metric-grid">
          <article className="metric-card"><strong>{metrics.running_tasks || 0}</strong><span>{tr('dashboard_running_tasks')}</span></article>
          <article className="metric-card"><strong>{metrics.completed_tasks || 0}</strong><span>{tr('dashboard_completed_tasks')}</span></article>
          <article className="metric-card"><strong>{metrics.credential_count || 0}</strong><span>{tr('dashboard_credential_count')}</span></article>
          <article className="metric-card"><strong>{metrics.proxy_count || 0}</strong><span>{tr('dashboard_proxy_count')}</span></article>
        </div>
        <article className="panel compact">
          <div className="panel-head">
            <div>
              <h3>{tr('panel_defaults_title')}</h3>
              <span>{tr('panel_defaults_desc')}</span>
            </div>
          </div>
          <form className="grid-two form-grid" onSubmit={handleDefaultsSubmit}>
            <label className="field-card">
              <span>{tr('default_gptmail')}</span>
              <select value={defaultsDraft.default_gptmail_credential_id} onChange={(event) => setDefaultsDraft((current) => ({ ...current, default_gptmail_credential_id: event.target.value }))}>
                <option value="">{tr('no_default_gptmail')}</option>
                {mailCredentials.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </label>
            <label className="field-card">
              <span>{tr('default_yescaptcha')}</span>
              <select value={defaultsDraft.default_yescaptcha_credential_id} onChange={(event) => setDefaultsDraft((current) => ({ ...current, default_yescaptcha_credential_id: event.target.value }))}>
                <option value="">{tr('no_default_yescaptcha')}</option>
                {captchaCredentials.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </label>
            <label className="field-card">
              <span>{tr('default_proxy')}</span>
              <select value={defaultsDraft.default_proxy_id} onChange={(event) => setDefaultsDraft((current) => ({ ...current, default_proxy_id: event.target.value }))}>
                <option value="">{tr('no_default_proxy')}</option>
                {statePayload.proxies.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </label>
            <div className="form-actions">
              <BusyButton type="submit" busy={isBusy('defaults-save')}>{tr('save_defaults')}</BusyButton>
            </div>
          </form>
        </article>
        <article className="panel compact">
          <div className="panel-head">
            <div>
              <h3>{tr('panel_recent_tasks_title')}</h3>
              <span>{tr('panel_recent_tasks_desc')}</span>
            </div>
          </div>
          <div className="simple-list">
            {(statePayload.dashboard.recent_tasks || []).length ? statePayload.dashboard.recent_tasks.map((task) => (
              <button
                key={task.id}
                type="button"
                className="simple-row"
                onClick={() => {
                  setSelectedTaskId(task.id);
                  setActiveSection('task-detail');
                }}
              >
                <span>{getTaskDisplayName(task)}</span>
                <span>{task.results_count}/{task.quantity} | {statusLabel(task.status)}</span>
              </button>
            )) : <p className="empty">{tr('empty_tasks')}</p>}
          </div>
        </article>
      </section>
    );
  }

  function renderCredentials() {
    return (
      <section className="section-card active">
        <div className="grid-two">
          <article className="panel">
            <div className="panel-head">
              <div>
                <h3>{tr('credentials_create_title')}</h3>
                <span>{tr('credentials_create_desc')}</span>
              </div>
            </div>
            <form className="stack" onSubmit={handleCredentialSubmit}>
              <label className="field-card">
                <span>{tr('field_name')}</span>
                <input required value={credentialDraft.name} onChange={(event) => setCredentialDraft((current) => ({ ...current, name: event.target.value }))} />
              </label>
              <label className="field-card">
                <span>{tr('field_kind')}</span>
                <select value={credentialDraft.kind} onChange={(event) => setCredentialDraft((current) => ({ ...current, kind: event.target.value }))}>
                  <option value="gptmail">{credentialKindLabel('gptmail')}</option>
                  <option value="moemail">{credentialKindLabel('moemail')}</option>
                  <option value="cloudflare_temp_email">{credentialKindLabel('cloudflare_temp_email')}</option>
                  <option value="yescaptcha">{credentialKindLabel('yescaptcha')}</option>
                </select>
              </label>
              <label className="field-card">
                <span>{credentialFieldMeta.apiKeyLabel}</span>
                <input required value={credentialDraft.api_key} onChange={(event) => setCredentialDraft((current) => ({ ...current, api_key: event.target.value }))} />
              </label>
              {credentialFieldMeta.hint ? (
                <>
                  <p className="field-tip field-tip--soft">{credentialFieldMeta.hint}</p>
                  <label className="field-card">
                    <span>{tr('field_base_url')}</span>
                    <input
                      required={credentialDraft.kind !== 'gptmail' && credentialFieldMeta.isEmail}
                      value={credentialDraft.base_url}
                      placeholder={tr('field_base_url_placeholder')}
                      onChange={(event) => setCredentialDraft((current) => ({ ...current, base_url: event.target.value }))}
                    />
                  </label>
                  <label className="field-card">
                    <span>{tr('field_prefix')}</span>
                    <input
                      value={credentialDraft.prefix}
                      placeholder={tr('field_prefix_placeholder')}
                      onChange={(event) => setCredentialDraft((current) => ({ ...current, prefix: event.target.value }))}
                    />
                  </label>
                  <label className="field-card">
                    <span>{tr('field_domain')}</span>
                    <input
                      value={credentialDraft.domain}
                      placeholder={tr('field_domain_placeholder')}
                      onChange={(event) => setCredentialDraft((current) => ({ ...current, domain: event.target.value }))}
                    />
                  </label>
                </>
              ) : null}
              {credentialFieldMeta.showSecret ? (
                <label className="field-card">
                  <span>{credentialFieldMeta.secretLabel}</span>
                  <input
                    value={credentialDraft.secret}
                    placeholder={credentialFieldMeta.secretPlaceholder}
                    onChange={(event) => setCredentialDraft((current) => ({ ...current, secret: event.target.value }))}
                  />
                </label>
              ) : null}
              <label className="field-card">
                <span>{tr('field_notes')}</span>
                <textarea rows="3" value={credentialDraft.notes} onChange={(event) => setCredentialDraft((current) => ({ ...current, notes: event.target.value }))} />
              </label>
              <BusyButton type="submit" busy={isBusy('credential-save')}>{tr('save_credential')}</BusyButton>
            </form>
          </article>
          <article className="panel">
            <div className="panel-head">
              <div>
                <h3>{tr('credentials_saved_title')}</h3>
                <span>{tr('credentials_saved_desc')}</span>
              </div>
            </div>
            <div className="entity-list">
              {statePayload.credentials.length ? statePayload.credentials.map((item) => {
                const isDefault = isEmailCredentialKind(item.kind)
                  ? statePayload.defaults.default_gptmail_credential_id === item.id
                  : statePayload.defaults.default_yescaptcha_credential_id === item.id;
                const defaultKey = isEmailCredentialKind(item.kind) ? 'default_gptmail_credential_id' : 'default_yescaptcha_credential_id';
                return (
                  <article className="entity-card" key={item.id}>
                    <div>
                      <h3>{item.name}</h3>
                      <p className="meta">{credentialKindLabel(item.kind)} | {tr('created_at', { value: item.created_at })}{isDefault ? ` | ${tr('default_badge')}` : ''}</p>
                      <p className="notes">{item.notes || ''}</p>
                    </div>
                    <div className="entity-actions">
                      <BusyButton type="button" busy={isBusy(`set-default-${defaultKey}-${item.id}`)} disabled={isDefault} onClick={() => handleSetDefault(defaultKey, item.id)}>
                        {isDefault ? tr('current_default') : tr('set_default')}
                      </BusyButton>
                      <BusyButton type="button" className="danger" busy={isBusy(`credential-delete-${item.id}`)} onClick={() => handleDeleteCredential(item)}>{tr('delete')}</BusyButton>
                    </div>
                  </article>
                );
              }) : <p className="empty">{tr('empty_credentials')}</p>}
            </div>
          </article>
        </div>
      </section>
    );
  }

  function renderProxies() {
    return (
      <section className="section-card active">
        <div className="grid-two">
          <article className="panel">
            <div className="panel-head">
              <div>
                <h3>{tr('proxies_create_title')}</h3>
                <span>{tr('proxies_create_desc')}</span>
              </div>
            </div>
            <form className="stack" onSubmit={handleProxySubmit}>
              <label className="field-card">
                <span>{tr('field_name')}</span>
                <input required value={proxyDraft.name} onChange={(event) => setProxyDraft((current) => ({ ...current, name: event.target.value }))} />
              </label>
              <label className="field-card">
                <span>{tr('field_proxy_url')}</span>
                <input required value={proxyDraft.proxy_url} onChange={(event) => setProxyDraft((current) => ({ ...current, proxy_url: event.target.value }))} />
              </label>
              <label className="field-card">
                <span>{tr('field_notes')}</span>
                <textarea rows="3" value={proxyDraft.notes} onChange={(event) => setProxyDraft((current) => ({ ...current, notes: event.target.value }))} />
              </label>
              <BusyButton type="submit" busy={isBusy('proxy-save')}>{tr('save_proxy')}</BusyButton>
            </form>
          </article>
          <article className="panel">
            <div className="panel-head">
              <div>
                <h3>{tr('proxies_saved_title')}</h3>
                <span>{tr('proxies_saved_desc')}</span>
              </div>
            </div>
            <div className="entity-list">
              {statePayload.proxies.length ? statePayload.proxies.map((item) => {
                const isDefault = statePayload.defaults.default_proxy_id === item.id;
                return (
                  <article className="entity-card" key={item.id}>
                    <div>
                      <h3>{item.name}</h3>
                      <p className="meta">{item.proxy_url}{isDefault ? ` | ${tr('default_badge')}` : ''}</p>
                      <p className="notes">{item.notes || ''}</p>
                    </div>
                    <div className="entity-actions">
                      <BusyButton type="button" busy={isBusy(`set-default-default_proxy_id-${item.id}`)} disabled={isDefault} onClick={() => handleSetDefault('default_proxy_id', item.id)}>
                        {isDefault ? tr('current_default') : tr('set_default')}
                      </BusyButton>
                      <BusyButton type="button" className="danger" busy={isBusy(`proxy-delete-${item.id}`)} onClick={() => handleDeleteProxy(item)}>{tr('delete')}</BusyButton>
                    </div>
                  </article>
                );
              }) : <p className="empty">{tr('empty_proxies')}</p>}
            </div>
          </article>
        </div>
      </section>
    );
  }

  function renderCreateTask() {
    return (
      <section className="section-card active">
        <article className="panel">
          <form className="grid-two form-grid" onSubmit={handleTaskSubmit}>
            <label className="field-card">
              <span>{tr('field_task_name')}</span>
              <input required value={taskDraft.name} onChange={(event) => setTaskDraft((current) => ({ ...current, name: event.target.value }))} />
            </label>
            <label className="field-card">
              <span>{tr('field_platform')}</span>
              <select
                value={taskDraft.platform}
                onChange={(event) => {
                  const nextPlatform = event.target.value;
                  const nextSpec = statePayload.platforms[nextPlatform] || {};
                  setTaskDraft((current) => normalizeTaskDraft({
                    ...current,
                    platform: nextPlatform,
                    concurrency: String(nextSpec.default_concurrency || current.concurrency || 1),
                  }, statePayload.platforms, statePayload.credentials, statePayload.proxies));
                }}
              >
                {Object.entries(statePayload.platforms).map(([key, item]) => <option key={key} value={key}>{item.label}</option>)}
              </select>
            </label>
            <label className="field-card">
              <span>{tr('field_quantity')}</span>
              <input type="number" min="1" max="100000" required value={taskDraft.quantity} onChange={(event) => setTaskDraft((current) => ({ ...current, quantity: event.target.value }))} />
            </label>
            <label className="field-card">
              <span>{tr('field_concurrency')}</span>
              <input type="number" min="1" max="64" value={taskDraft.concurrency} onChange={(event) => setTaskDraft((current) => ({ ...current, concurrency: event.target.value }))} />
            </label>
            {currentPlatformSpec.requires_email_credential ? (
              <label className="field-card">
                <span>{tr('field_email_credential')}</span>
                <select value={taskDraft.email_credential_id} onChange={(event) => setTaskDraft((current) => ({ ...current, email_credential_id: event.target.value }))}>
                  <option value="">{tr('use_default_gptmail')}</option>
                  {mailCredentials.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </label>
            ) : null}
            {currentPlatformSpec.requires_captcha_credential ? (
              <label className="field-card">
                <span>{tr('field_captcha_credential')}</span>
                <select value={taskDraft.captcha_credential_id} onChange={(event) => setTaskDraft((current) => ({ ...current, captcha_credential_id: event.target.value }))}>
                  <option value="">{tr('use_default_yescaptcha')}</option>
                  {captchaCredentials.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </label>
            ) : null}
            <label className="field-card">
              <span>{tr('field_proxy_mode')}</span>
              <select
                value={taskDraft.proxy_mode}
                onChange={(event) => setTaskDraft((current) => normalizeTaskDraft({ ...current, proxy_mode: event.target.value }, statePayload.platforms, statePayload.credentials, statePayload.proxies))}
                disabled={!currentPlatformSpec.supports_proxy}
              >
                <option value="none">{tr('proxy_mode_none')}</option>
                <option value="default">{tr('proxy_mode_default')}</option>
                <option value="custom">{tr('proxy_mode_custom')}</option>
              </select>
            </label>
            {currentPlatformSpec.supports_proxy && taskDraft.proxy_mode === 'custom' ? (
              <label className="field-card">
                <span>{tr('field_proxy_select')}</span>
                <select value={taskDraft.proxy_id} onChange={(event) => setTaskDraft((current) => ({ ...current, proxy_id: event.target.value }))}>
                  <option value="">{tr('choose_proxy')}</option>
                  {statePayload.proxies.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </label>
            ) : null}
            <div className="form-actions full-row">
              <BusyButton type="submit" busy={isBusy('task-save')}>{tr('save_task')}</BusyButton>
            </div>
          </form>
        </article>
      </section>
    );
  }

  function renderTaskDetail() {
    const scheduleSummary = visibleTask ? getScheduleTaskSummary(visibleTask) : null;
    const scheduleDetail = visibleSchedule ? getScheduleDetail(visibleSchedule) : null;
    return (
      <section className="section-card active">
        <p className="subtle task-detail-note content-section-note">{tr('task_detail_note')}</p>
        <div className="detail-layout">
          <aside className="task-side-wrap">
            <article className="panel task-side-panel">
              <div className="panel-head panel-head--stack">
                <div>
                  <h3>{tr('task_list_title')}</h3>
                  <span>{tr('task_list_desc')}</span>
                </div>
              </div>
              <div className="task-filter-bar task-filter-grid">
                <label className="field-card field-card--compact">
                  <span>{tr('task_list_mode')}</span>
                  <select value={taskListMode} onChange={(event) => setTaskListMode(event.target.value)}>
                    <option value="task">{tr('task_list_mode_task')}</option>
                    <option value="schedule">{tr('task_list_mode_schedule')}</option>
                  </select>
                </label>
                {taskListMode === 'task' ? (
                <label className="field-card field-card--compact">
                  <span>{tr('task_filter_status')}</span>
                  <select value={taskFilterStatus} onChange={(event) => setTaskFilterStatus(event.target.value)}>
                    {TASK_STATUSES.map((status) => (
                      <option key={status} value={status}>{status === 'all' ? tr('task_filter_all') : statusLabel(status)}</option>
                    ))}
                  </select>
                </label>
                ) : null}
              </div>
              <div className="task-side-list">
                {taskListMode === 'task' ? filteredTasks.length ? filteredTasks.map((task) => (
                  <button key={task.id} type="button" className={`task-side-item ${visibleTask?.id === task.id ? 'selected' : ''}`.trim()} onClick={() => setSelectedTaskId(task.id)}>
                    <div className="task-side-item__top">
                      <strong className="task-side-item__name">{getTaskDisplayName(task)}</strong>
                      <span className="task-side-item__id">#{task.id}</span>
                    </div>
                    <div className="task-side-item__meta">
                      <span className="task-side-item__count">{task.results_count}/{task.quantity}</span>
                      <span className={`status-pill status-pill--${task.status}`}>{statusLabel(task.status)}</span>
                    </div>
                  </button>
                )) : <p className="empty">{tr('empty_filtered_tasks')}</p> : statePayload.schedules.length ? statePayload.schedules.map((schedule) => {
                  const detail = getScheduleDetail(schedule);
                  return (
                    <button key={schedule.id} type="button" className={`task-side-item ${visibleSchedule?.id === schedule.id ? 'selected' : ''}`.trim()} onClick={() => setSelectedScheduleId(schedule.id)}>
                      <div className="task-side-item__top">
                        <strong className="task-side-item__name">{schedule.name} {tr('schedule_tag_suffix')}</strong>
                        <span className="task-side-item__id">#{schedule.id}</span>
                      </div>
                      <div className="task-side-item__meta">
                        <span className="task-side-item__count">{detail?.completedRuns || 0} {tr('schedule_runs_short')}</span>
                        <span className={`status-pill ${schedule.enabled ? 'status-pill--linked' : 'status-pill--disabled'}`.trim()}>
                          {schedule.enabled ? tr('enable') : tr('disable')}
                        </span>
                      </div>
                    </button>
                  );
                }) : <p className="empty">{tr('empty_schedules')}</p>}
              </div>
            </article>
          </aside>
          <article className="panel task-detail-panel">
            {taskListMode === 'task' && visibleTask ? (
              <>
                <div className={`task-detail-header ${scheduleSummary ? 'task-detail-header--split' : ''}`.trim()}>
                  <div className="task-detail-header-main">
                    <h3>{getTaskDisplayName(visibleTask)} (#{visibleTask.id})</h3>
                    <p className="meta">{tr('task_header_meta', {
                      platform: visibleTask.platform,
                      quantity: visibleTask.quantity,
                      completed: visibleTask.results_count,
                      status: statusLabel(visibleTask.status),
                    })}</p>
                  </div>
                  {scheduleSummary ? (
                    <aside className="schedule-summary-card">
                      <strong>{tr('schedule_detail_title')}</strong>
                      <p className="meta">{scheduleSummary.schedule.name}</p>
                      <div className="schedule-summary-list">
                        <span>{scheduleSummary.schedule.platform}</span>
                        <span>{tr('schedule_target_quantity', { value: scheduleSummary.todayTask?.quantity ?? scheduleSummary.schedule.quantity })}</span>
                        <span>{tr('schedule_completed_quantity', { value: scheduleSummary.todayTask?.results_count ?? 0 })}</span>
                        <span>{tr('schedule_today_status', { value: scheduleSummary.todayTask ? statusLabel(scheduleSummary.todayTask.status) : tr('schedule_today_none') })}</span>
                        <span>{tr('schedule_completed_runs', { value: scheduleSummary.completedRuns })}</span>
                      </div>
                    </aside>
                  ) : null}
                </div>
                <div className="task-actions">
                  <BusyButton type="button" busy={isBusy(`task-stop-${visibleTask.id}`)} disabled={!['queued', 'running', 'stopping'].includes(visibleTask.status)} onClick={() => handleStopTask(visibleTask)}>{tr('stop_task')}</BusyButton>
                  <button type="button" disabled={['queued', 'running', 'stopping'].includes(visibleTask.status)} onClick={() => window.open(`/api/tasks/${visibleTask.id}/download`, '_blank')}>{tr('download_zip')}</button>
                  <BusyButton type="button" className="danger" busy={isBusy(`task-delete-${visibleTask.id}`)} disabled={['queued', 'running', 'stopping'].includes(visibleTask.status)} onClick={() => handleDeleteTask(visibleTask)}>{tr('delete_task')}</BusyButton>
                  {statePayload.cpamc?.enabled && statePayload.cpamc?.linked ? (
                    <BusyButton
                      type="button"
                      className="ghost-btn"
                      busy={isBusy(`cpamc-import-${visibleTask.id}`)}
                      disabled={!visibleTask.cpamc_importable_count}
                      title={!visibleTask.cpamc_importable_count ? tr('cpamc_import_disabled') : ''}
                      onClick={() => handleImportTaskToCpamc(visibleTask)}
                    >
                      {tr('cpamc_import_button')}
                    </BusyButton>
                  ) : null}
                </div>
                <div className="console-box large-console">
                  <div className="console-title">{tr('console_title')}</div>
                  <pre id="task-console" ref={consoleRef}>{visibleTask.console_tail || tr('console_empty')}</pre>
                </div>
              </>
            ) : taskListMode === 'schedule' && visibleSchedule ? (
              <div className="schedule-detail-layout">
                <div className="task-detail-header">
                  <div className="task-detail-header-main">
                    <h3>{visibleSchedule.name} {tr('schedule_tag_suffix')} (#{visibleSchedule.id})</h3>
                    <p className="meta">
                      {visibleSchedule.platform} | {tr('schedule_target_quantity', { value: visibleSchedule.quantity })} | {tr('schedule_completed_quantity', { value: scheduleDetail?.todayTask?.results_count ?? 0 })} | {tr('schedule_today_status', { value: scheduleDetail?.todayTask ? statusLabel(scheduleDetail.todayTask.status) : tr('schedule_today_none') })}
                    </p>
                    <p className="notes">
                      {tr('schedule_completed_runs', { value: scheduleDetail?.completedRuns ?? 0 })} | {visibleSchedule.use_proxy ? tr('schedule_proxy_on') : tr('schedule_proxy_off')} | {visibleSchedule.auto_import_cpamc ? tr('schedule_cpamc_auto_import_on') : tr('schedule_cpamc_auto_import_off')}
                    </p>
                  </div>
                </div>
                <div className="task-actions">
                  <BusyButton type="button" busy={isBusy(`schedule-run-${visibleSchedule.id}`)} onClick={() => handleRunScheduleNow(visibleSchedule)}>{tr('run_schedule_now')}</BusyButton>
                  <BusyButton type="button" busy={isBusy(`schedule-toggle-${visibleSchedule.id}`)} onClick={() => handleToggleSchedule(visibleSchedule)}>{visibleSchedule.enabled ? tr('disable') : tr('enable')}</BusyButton>
                  <BusyButton type="button" className="danger" busy={isBusy(`schedule-delete-${visibleSchedule.id}`)} onClick={() => handleDeleteSchedule(visibleSchedule)}>{tr('delete')}</BusyButton>
                  {statePayload.cpamc?.enabled && statePayload.cpamc?.linked ? (
                    <BusyButton
                      type="button"
                      className="ghost-btn"
                      busy={isBusy(`cpamc-import-${scheduleDetail?.importTask?.id}`)}
                      disabled={!scheduleDetail?.importTask}
                      title={!scheduleDetail?.importTask ? tr('cpamc_import_disabled') : ''}
                      onClick={() => handleImportTaskToCpamc(scheduleDetail.importTask)}
                    >
                      {tr('cpamc_import_button')}
                    </BusyButton>
                  ) : null}
                </div>
                <div className="console-box large-console">
                  <div className="console-title">{tr('console_title')}</div>
                  <pre>{scheduleDetail?.todayTask?.console_tail || tr('schedule_console_empty')}</pre>
                </div>
              </div>
            ) : (
              <div className="task-empty">
                <h3>{tr('task_detail_empty_title')}</h3>
                <p className="meta">{tr('task_detail_empty_desc')}</p>
              </div>
            )}
          </article>
        </div>
      </section>
    );
  }

  function renderSchedules() {
    return (
      <section className="section-card active">
        <div className="grid-two">
          <article className="panel">
            <div className="panel-head">
              <div>
                <h3>{tr('schedules_create_title')}</h3>
                <span>{tr('schedules_create_desc')}</span>
              </div>
            </div>
            <form className="stack" onSubmit={handleScheduleSubmit}>
              <label className="field-card">
                <span>{tr('field_name')}</span>
                <input required value={scheduleDraft.name} onChange={(event) => setScheduleDraft((current) => ({ ...current, name: event.target.value }))} />
              </label>
              <label className="field-card">
                <span>{tr('field_platform')}</span>
                <select value={scheduleDraft.platform} onChange={(event) => setScheduleDraft((current) => ({ ...current, platform: event.target.value }))}>
                  {Object.entries(statePayload.platforms).map(([key, item]) => <option key={key} value={key}>{item.label}</option>)}
                </select>
              </label>
              <label className="field-card">
                <span>{tr('field_quantity')}</span>
                <input type="number" min="1" max="100000" required value={scheduleDraft.quantity} onChange={(event) => setScheduleDraft((current) => ({ ...current, quantity: event.target.value }))} />
              </label>
              <label className="field-card">
                <span>{tr('field_concurrency')}</span>
                <input type="number" min="1" max="64" value={scheduleDraft.concurrency} onChange={(event) => setScheduleDraft((current) => ({ ...current, concurrency: event.target.value }))} />
              </label>
              <label className="field-card">
                <span>{tr('field_time_of_day')}</span>
                <input type="time" required value={scheduleDraft.time_of_day} onChange={(event) => setScheduleDraft((current) => ({ ...current, time_of_day: event.target.value }))} />
              </label>
              <label className="checkbox-row field-card field-card--checkbox">
                <input type="checkbox" checked={scheduleDraft.use_proxy} onChange={(event) => setScheduleDraft((current) => ({ ...current, use_proxy: event.target.checked }))} />
                <span>{tr('field_use_default_proxy')}</span>
              </label>
              <label className="checkbox-row field-card field-card--checkbox">
                <input type="checkbox" checked={scheduleDraft.auto_import_cpamc} onChange={(event) => setScheduleDraft((current) => ({ ...current, auto_import_cpamc: event.target.checked }))} />
                <span>{tr('field_schedule_auto_import_cpamc')}</span>
              </label>
              <BusyButton type="submit" busy={isBusy('schedule-save')}>{tr('save_schedule')}</BusyButton>
            </form>
          </article>
          <article className="panel">
            <div className="panel-head">
              <div>
                <h3>{tr('schedules_saved_title')}</h3>
                <span>{tr('schedules_saved_desc')}</span>
              </div>
            </div>
            <div className="entity-list">
              {statePayload.schedules.length ? statePayload.schedules.map((item) => (
                <article className="entity-card" key={item.id}>
                  <div>
                    <h3>{item.name}</h3>
                    <p className="meta">{tr('schedule_meta', {
                      platform: item.platform,
                      time: item.time_of_day,
                      quantity: item.quantity,
                      enabled: item.enabled ? tr('enable') : tr('disable'),
                    })}</p>
                    <p className="notes">{item.use_proxy ? tr('schedule_proxy_on') : tr('schedule_proxy_off')}</p>
                    <p className="notes">{item.auto_import_cpamc ? tr('schedule_cpamc_auto_import_on') : tr('schedule_cpamc_auto_import_off')}</p>
                  </div>
                  <div className="entity-actions">
                    <BusyButton type="button" busy={isBusy(`schedule-toggle-${item.id}`)} onClick={() => handleToggleSchedule(item)}>{item.enabled ? tr('disable') : tr('enable')}</BusyButton>
                    <BusyButton type="button" className="danger" busy={isBusy(`schedule-delete-${item.id}`)} onClick={() => handleDeleteSchedule(item)}>{tr('delete')}</BusyButton>
                  </div>
                </article>
              )) : <p className="empty">{tr('empty_schedules')}</p>}
            </div>
          </article>
        </div>
      </section>
    );
  }

  function renderCpamc() {
    const cpamcStatus = cpamcDraft.enabled
      ? (cpamcDraft.linked ? tr('cpamc_status_linked') : tr('cpamc_status_unlinked'))
      : tr('cpamc_status_disabled');
    const cpamcStatusClass = cpamcDraft.enabled
      ? (cpamcDraft.linked ? 'status-pill--linked' : 'status-pill--queued')
      : 'status-pill--disabled';
    return (
      <section className="section-card active">
        <article className="panel">
          <div className="panel-head">
            <div>
              <h3>{tr('cpamc_title')}</h3>
              <span>{tr('cpamc_desc')}</span>
            </div>
            <div className="cpamc-head-actions">
              <label className={`cpamc-switch ${cpamcDraft.enabled ? 'is-enabled' : ''}`.trim()}>
                <input
                  type="checkbox"
                  checked={cpamcDraft.enabled}
                  onChange={(event) => {
                    setCpamcDirty(true);
                    setCpamcDraft((current) => ({
                      ...current,
                      enabled: event.target.checked,
                      linked: false,
                      last_error: '',
                    }));
                  }}
                />
                <span className="cpamc-switch-track" aria-hidden="true">
                  <span className="cpamc-switch-thumb" />
                </span>
                <span className="cpamc-switch-label">{tr('field_cpamc_enabled')}</span>
              </label>
              <span className={`status-pill ${cpamcStatusClass}`.trim()}>{cpamcStatus}</span>
            </div>
          </div>
          <form className="stack" onSubmit={handleCpamcSave}>
            <label className="checkbox-row field-card field-card--checkbox">
              <input
                type="checkbox"
                checked={cpamcDraft.auto_import_enabled}
                onChange={(event) => {
                  setCpamcDirty(true);
                  setCpamcDraft((current) => ({
                    ...current,
                    auto_import_enabled: event.target.checked,
                  }));
                }}
              />
              <span>{tr('field_cpamc_auto_import')}</span>
            </label>
            <p className="field-tip">{tr('cpamc_auto_import_hint')}</p>
            <label className="field-card">
              <span>{tr('field_cpamc_base_url')}</span>
              <input
                required={cpamcDraft.enabled}
                value={cpamcDraft.base_url}
                placeholder={tr('field_cpamc_base_url_placeholder')}
                onChange={(event) => {
                  setCpamcDirty(true);
                  setCpamcDraft((current) => ({
                    ...current,
                    base_url: event.target.value,
                    linked: false,
                    last_error: '',
                  }));
                }}
              />
            </label>
            <label className="field-card">
              <span>{tr('field_cpamc_management_key')}</span>
              <input
                type="password"
                required={cpamcDraft.enabled}
                value={cpamcDraft.management_key}
                placeholder={tr('field_cpamc_management_key_placeholder')}
                onChange={(event) => {
                  setCpamcDirty(true);
                  setCpamcDraft((current) => ({
                    ...current,
                    management_key: event.target.value,
                    linked: false,
                    last_error: '',
                  }));
                }}
              />
            </label>
            {cpamcDraft.last_error ? <p className="field-tip">{tr('cpamc_last_error', { value: cpamcDraft.last_error })}</p> : null}
            <div className="form-actions">
              <BusyButton type="submit" className="ghost-btn" busy={isBusy('cpamc-save')}>{tr('save_cpamc')}</BusyButton>
              <BusyButton type="button" busy={isBusy('cpamc-test')} onClick={handleCpamcTest}>{tr('test_cpamc')}</BusyButton>
            </div>
          </form>
        </article>
      </section>
    );
  }

  function renderApiKeys() {
    const apiKeys = statePayload.apiKeys || [];
    return (
      <section className="section-card active">
        <div className="grid-two">
          <article className="panel">
            <div className="panel-head">
              <div>
                <h3>{tr('api_create_title')}</h3>
                <span>{tr('api_create_desc')}</span>
              </div>
            </div>
            <form className="stack" onSubmit={handleApiKeySubmit}>
              <label className="field-card">
                <span>{tr('field_name')}</span>
                <input required value={apiKeyName} onChange={(event) => setApiKeyName(event.target.value)} />
              </label>
              <BusyButton type="submit" busy={isBusy('api-key-save')}>{tr('save_api_key')}</BusyButton>
            </form>
            {flashKey ? (
              <div className="flash-key">
                <strong>{tr('save_now')}</strong>
                <code>{flashKey}</code>
              </div>
            ) : null}
          </article>
          <article className="panel">
            <div className="panel-head">
              <div>
                <h3>{tr('api_saved_title')}</h3>
                <span>{tr('api_saved_desc')}</span>
              </div>
            </div>
            <div className="entity-list">
              {apiKeys.length ? apiKeys.map((item) => (
                <article className="entity-card" key={item.id}>
                  <div>
                    <h3>{item.name}</h3>
                    <p className="meta">{tr('api_key_meta', { prefix: item.key_prefix, created_at: item.created_at })}</p>
                    <p className="notes">{item.last_used_at ? tr('last_used_at', { value: item.last_used_at }) : tr('unused')}</p>
                  </div>
                  <div className="entity-actions">
                    <BusyButton type="button" className="danger" busy={isBusy(`api-key-delete-${item.id}`)} onClick={() => handleDeleteApiKey(item)}>{tr('delete')}</BusyButton>
                  </div>
                </article>
              )) : <p className="empty">{tr('empty_api_keys')}</p>}
            </div>
          </article>
        </div>
      </section>
    );
  }

  function renderDocs() {
    const isZh = String(APP_CONFIG.uiLang || '').toLowerCase().startsWith('zh');
    const apiBaseUrl = APP_CONFIG.apiBaseUrl || 'http://127.0.0.1:8000';
    const docs = isZh ? {
      heroTitle: '外部任务接口说明',
      heroText: '这里仅保留 API 文档。部署方式、初始化流程和日常使用说明已整理到 README，后台页面只负责给你可直接调用的接口信息。',
      flowTitle: '推荐调用流程',
      flowText: '建议先在后台创建 API Key，再从外部程序调用公开接口。不要绕过控制台直接写数据库。',
      flowSteps: [
        '在后台“API”页面生成并保存 API Key。',
        '调用 `POST /api/external/tasks` 创建任务。',
        '轮询 `GET /api/external/tasks/{task_id}` 查看状态、完成数量与下载地址。',
        '任务完成后调用 `GET /api/external/tasks/{task_id}/download` 下载结果压缩包。',
      ],
      endpointTitle: '接口列表',
      endpointHeaders: ['方法', '路径', '说明'],
      endpoints: [
        ['POST', '/api/external/tasks', '创建新的外部任务'],
        ['GET', '/api/external/tasks/{task_id}', '查询任务状态、完成数量与下载地址'],
        ['GET', '/api/external/tasks/{task_id}/download', '下载任务结果压缩包'],
      ],
      paramsTitle: '创建任务参数',
      paramHeaders: ['字段', '类型', '必填', '说明'],
      params: [
        ['platform', 'string', '是', '支持 `chatgpt-register-v2` 与 `grok-register`'],
        ['quantity', 'integer', '是', '目标成功数量，按真实成功数统计'],
        ['use_proxy', 'boolean', '否', '是否使用后台默认代理'],
        ['concurrency', 'integer', '否', '并发数，默认 `1`'],
        ['name', 'string', '否', '自定义任务名称'],
      ],
      notesTitle: '返回说明',
      notes: [
        '`completed_count` 表示真实成功数，不按尝试次数累计。',
        '`download_url` 只有在任务完成并生成压缩包后才会返回。',
        '通过 API 创建的任务会在 `auto_delete_at` 指定时间后自动清理。',
        `以下示例默认以 ${apiBaseUrl} 作为接口地址。`,
      ],
      createTitle: '创建任务示例',
      createHttp: `POST ${apiBaseUrl}/api/external/tasks
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "platform": "chatgpt-register-v2",
  "quantity": 10,
  "use_proxy": true,
  "concurrency": 1,
  "name": "chatgpt-batch-01"
}`,
      createCurl: `curl -X POST "${apiBaseUrl}/api/external/tasks" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d "{\\"platform\\":\\"chatgpt-register-v2\\",\\"quantity\\":10,\\"use_proxy\\":true,\\"concurrency\\":1,\\"name\\":\\"chatgpt-batch-01\\"}"`,
      queryTitle: '查询任务示例',
      queryHttp: `GET ${apiBaseUrl}/api/external/tasks/TASK_ID
Authorization: Bearer YOUR_API_KEY`,
      queryCurl: `curl "${apiBaseUrl}/api/external/tasks/TASK_ID" \\
  -H "Authorization: Bearer YOUR_API_KEY"`,
      queryJson: `{
  "task_id": 12,
  "status": "running",
  "completed_count": 4,
  "target_quantity": 10,
  "auto_delete_at": "2026-03-21 20:15:00",
  "download_url": null
}`,
      downloadTitle: '下载结果示例',
      downloadHttp: `GET ${apiBaseUrl}/api/external/tasks/TASK_ID/download
Authorization: Bearer YOUR_API_KEY`,
      downloadCurl: `curl -L "${apiBaseUrl}/api/external/tasks/TASK_ID/download" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -o result.zip`,
    } : {
      heroTitle: 'External Task API Reference',
      heroText: 'Only the API guide remains here. Deployment, initialization, and daily workflow notes are now kept in the README.',
      flowTitle: 'Recommended Workflow',
      flowText: 'Create an API key in the console first, then call the public API from your external service. Do not write to the database directly.',
      flowSteps: [
        'Generate and save an API key in the console.',
        'Call `POST /api/external/tasks` to create a task.',
        'Poll `GET /api/external/tasks/{task_id}` for status, completion count, and download URL.',
        'Call `GET /api/external/tasks/{task_id}/download` after completion.',
      ],
      endpointTitle: 'Endpoints',
      endpointHeaders: ['Method', 'Path', 'Description'],
      endpoints: [
        ['POST', '/api/external/tasks', 'Create a new external task'],
        ['GET', '/api/external/tasks/{task_id}', 'Query task status, completion count, and download URL'],
        ['GET', '/api/external/tasks/{task_id}/download', 'Download the task result archive'],
      ],
      paramsTitle: 'Create Task Parameters',
      paramHeaders: ['Field', 'Type', 'Required', 'Description'],
      params: [
        ['platform', 'string', 'yes', 'Supports `chatgpt-register-v2` and `grok-register`'],
        ['quantity', 'integer', 'yes', 'Target success count'],
        ['use_proxy', 'boolean', 'no', 'Whether to use the configured default proxy'],
        ['concurrency', 'integer', 'no', 'Concurrency, default is `1`'],
        ['name', 'string', 'no', 'Custom task name'],
      ],
      notesTitle: 'Response Notes',
      notes: [
        '`completed_count` is the real success count.',
        '`download_url` appears only after the task finishes and the archive is generated.',
        'API-created tasks are cleaned up automatically after `auto_delete_at`.',
        `Examples below use ${apiBaseUrl} as the base URL.`,
      ],
      createTitle: 'Create Task Example',
      createHttp: `POST ${apiBaseUrl}/api/external/tasks
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "platform": "chatgpt-register-v2",
  "quantity": 10,
  "use_proxy": true,
  "concurrency": 1,
  "name": "chatgpt-batch-01"
}`,
      createCurl: `curl -X POST "${apiBaseUrl}/api/external/tasks" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d "{\\"platform\\":\\"chatgpt-register-v2\\",\\"quantity\\":10,\\"use_proxy\\":true,\\"concurrency\\":1,\\"name\\":\\"chatgpt-batch-01\\"}"`,
      queryTitle: 'Query Task Example',
      queryHttp: `GET ${apiBaseUrl}/api/external/tasks/TASK_ID
Authorization: Bearer YOUR_API_KEY`,
      queryCurl: `curl "${apiBaseUrl}/api/external/tasks/TASK_ID" \\
  -H "Authorization: Bearer YOUR_API_KEY"`,
      queryJson: `{
  "task_id": 12,
  "status": "running",
  "completed_count": 4,
  "target_quantity": 10,
  "auto_delete_at": "2026-03-21 20:15:00",
  "download_url": null
}`,
      downloadTitle: 'Download Result Example',
      downloadHttp: `GET ${apiBaseUrl}/api/external/tasks/TASK_ID/download
Authorization: Bearer YOUR_API_KEY`,
      downloadCurl: `curl -L "${apiBaseUrl}/api/external/tasks/TASK_ID/download" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -o result.zip`,
    };
    const feature = isZh ? {
      title: '新增功能：日志',
      text: 'MREGISTER 现在把任务日志放到更直观的位置。创建任务后可以直接进入任务详情，持续查看脚本启动、运行、报错和收尾输出，不需要回到命令行窗口手动追踪。',
      items: [
        '支持实时查看当前任务输出。',
        '任务结束后仍可回看已保存的历史日志。',
        '更适合排查导入失败、凭据异常、网络问题和脚本执行中断。',
      ],
      imageAlt: 'MREGISTER 日志功能预览',
    } : {
      title: 'New Feature: Logs',
      text: 'MREGISTER now exposes task logs in a clearer workflow. After creating a task, you can open Task Detail to follow startup output, runtime progress, errors, and final export messages without tailing the CLI manually.',
      items: [
        'Inspect live task output in real time.',
        'Review persisted logs after the task finishes.',
        'Useful for diagnosing import failures, credential issues, network problems, and interrupted runs.',
      ],
      imageAlt: 'MREGISTER log feature preview',
    };

    return (
      <section className="section-card active">
        <article className="panel docs-panel">
          <section className="docs-hero">
            <h3>{docs.heroTitle}</h3>
            <p>{docs.heroText}</p>
          </section>

          <section className="doc-card doc-feature">
            <div>
              <h3>{feature.title}</h3>
              <p>{feature.text}</p>
              <ul className="doc-note-list">
                {feature.items.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
            <div className="doc-media-frame">
              <img className="doc-media" src={DOCS_LOG_IMAGE_SRC} alt={feature.imageAlt} />
            </div>
          </section>

          <section className="doc-card">
            <h3>{docs.flowTitle}</h3>
            <p>{docs.flowText}</p>
            <ol className="doc-step-list">
              {docs.flowSteps.map((item) => <li key={item}>{item}</li>)}
            </ol>
          </section>

          <div className="docs-grid">
            <section className="doc-card">
              <h3>{docs.endpointTitle}</h3>
              <div className="doc-table-wrap">
                <table className="doc-table">
                  <thead>
                    <tr>
                      {docs.endpointHeaders.map((item) => <th key={item}>{item}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {docs.endpoints.map(([method, path, desc]) => (
                      <tr key={`${method}-${path}`}>
                        <td>{method}</td>
                        <td><code>{path}</code></td>
                        <td>{desc}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="doc-card">
              <h3>{docs.paramsTitle}</h3>
              <div className="doc-table-wrap">
                <table className="doc-table">
                  <thead>
                    <tr>
                      {docs.paramHeaders.map((item) => <th key={item}>{item}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {docs.params.map(([field, type, required, desc]) => (
                      <tr key={field}>
                        <td><code>{field}</code></td>
                        <td>{type}</td>
                        <td>{required}</td>
                        <td>{desc}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <section className="doc-card">
            <h3>{docs.notesTitle}</h3>
            <ul className="doc-note-list">
              {docs.notes.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </section>

          <div className="docs-grid">
            <section className="doc-card">
              <h3>{docs.createTitle}</h3>
              <div className="doc-code-block">
                <span className="doc-code-label">HTTP</span>
                <pre className="doc-pre">{docs.createHttp}</pre>
              </div>
              <div className="doc-code-block">
                <span className="doc-code-label">curl</span>
                <pre className="doc-pre">{docs.createCurl}</pre>
              </div>
            </section>

            <section className="doc-card">
              <h3>{docs.queryTitle}</h3>
              <div className="doc-code-block">
                <span className="doc-code-label">HTTP</span>
                <pre className="doc-pre">{docs.queryHttp}</pre>
              </div>
              <div className="doc-code-block">
                <span className="doc-code-label">curl</span>
                <pre className="doc-pre">{docs.queryCurl}</pre>
              </div>
              <div className="doc-code-block">
                <span className="doc-code-label">JSON</span>
                <pre className="doc-pre">{docs.queryJson}</pre>
              </div>
            </section>

            <section className="doc-card">
              <h3>{docs.downloadTitle}</h3>
              <div className="doc-code-block">
                <span className="doc-code-label">HTTP</span>
                <pre className="doc-pre">{docs.downloadHttp}</pre>
              </div>
              <div className="doc-code-block">
                <span className="doc-code-label">curl</span>
                <pre className="doc-pre">{docs.downloadCurl}</pre>
              </div>
            </section>
          </div>
        </article>
      </section>
    );
  }

  function renderContent() {
    if (loadError && !loaded) {
      return <section className="section-card active"><div className="panel"><p className="empty">{loadError}</p></div></section>;
    }
    switch (activeSection) {
      case 'dashboard':
        return renderDashboard();
      case 'credentials':
        return renderCredentials();
      case 'proxies':
        return renderProxies();
      case 'create-task':
        return renderCreateTask();
      case 'task-detail':
        return renderTaskDetail();
      case 'schedules':
        return renderSchedules();
      case 'cpamc':
        return renderCpamc();
      case 'api-keys':
        return renderApiKeys();
      case 'docs':
        return renderDocs();
      default:
        return renderDashboard();
    }
  }

  return (
    <>
      <div className={`admin-shell ${sidebarCollapsed && !isMobileLayout() ? 'sidebar-collapsed' : ''} ${sidebarOpen ? 'sidebar-open' : ''}`}>
        <aside className="sidebar">
          <div className="sidebar-top">
            <div className="sidebar-brand">
              <div className="brand-logo-wrap">
                <img className="brand-logo" src={SIDEBAR_LOGO_SRC} alt={tr('brand_name')} />
              </div>
              <div className="brand-copy">
                <h1>{tr('brand_name')}</h1>
              </div>
            </div>
          </div>
          <nav className="sidebar-nav">
            {NAV_ITEMS.map(([sectionId, labelKey]) => {
              const label = tr(labelKey);
              return (
                <button
                  key={sectionId}
                  type="button"
                  title={label}
                  className={`nav-btn ${activeSection === sectionId ? 'active' : ''}`.trim()}
                  onClick={() => switchSection(sectionId)}
                >
                  <span className="nav-btn__icon" aria-hidden="true"><SidebarIcon name={sectionId} /></span>
                  <span className="nav-btn__label">{label}</span>
                </button>
              );
            })}
          </nav>
          <BusyButton type="button" className="sidebar-logout" busy={isBusy('logout')} onClick={handleLogout} title={logoutLabel}>
            <span className="nav-btn__icon" aria-hidden="true"><SidebarIcon name="logout" /></span>
            <span className="nav-btn__label">{logoutLabel}</span>
          </BusyButton>
          <div className="sidebar-footer">
            <button
              type="button"
              className="sidebar-footer-toggle"
              aria-label={tr('toggle_sidebar')}
              title={tr('toggle_sidebar')}
              onClick={() => {
                if (isMobileLayout()) {
                  setSidebarOpen((current) => !current);
                } else {
                  setSidebarCollapsed((current) => !current);
                }
              }}
            >
              <span className="nav-btn__icon sidebar-toggle-glyph" aria-hidden="true">{sidebarCollapsed && !isMobileLayout() ? '>' : '<'}</span>
              <span className="nav-btn__label">{tr('toggle_sidebar')}</span>
            </button>
          </div>
        </aside>
        <button type="button" className="sidebar-overlay" aria-label={tr('close_sidebar')} onClick={() => setSidebarOpen(false)} />
        <main className="content-shell">
          <div className="content-topbar">
            <button type="button" className="mobile-nav-btn" aria-label={tr('open_sidebar')} onClick={() => setSidebarOpen(true)}>
              <span className="mobile-nav-glyph" aria-hidden="true">
                <span />
                <span />
                <span />
              </span>
            </button>
            <div className="content-topbar-copy">
              {topbarBreadcrumbs.map((item, index) => (
                <React.Fragment key={`${item}-${index}`}>
                  {index ? <span className="content-breadcrumb-sep" aria-hidden="true">&gt;</span> : null}
                  <span className={`content-breadcrumb ${index === topbarBreadcrumbs.length - 1 ? 'content-breadcrumb--current' : ''}`.trim()}>
                    {item}
                  </span>
                </React.Fragment>
              ))}
            </div>
            <a
              className="topbar-link"
              href={PROJECT_GITHUB_URL}
              target="_blank"
              rel="noreferrer"
              aria-label="Open GitHub project"
              title="GitHub"
            >
              <GithubIcon />
            </a>
          </div>
          {flashNotice && loaded ? <div className={`toast-banner toast-banner--${flashNotice.type}`.trim()}>{flashNotice.message}</div> : null}
          {loadError && loaded ? <div className="toast-error">{loadError}</div> : null}
          {!loaded ? <section className="section-card active"><div className="panel"><p className="empty">Loading...</p></div></section> : renderContent()}
        </main>
      </div>
      <Modal
        open={Boolean(modalState)}
        title={modalState?.title || ''}
        message={modalState?.message || ''}
        confirmLabel={modalState?.confirmLabel || tr('created_task_modal_confirm')}
        cancelLabel={modalState?.cancelLabel}
        onConfirm={() => closeModal(true)}
        onCancel={() => closeModal(false)}
      />
    </>
  );
}
