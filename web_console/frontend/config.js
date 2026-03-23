export const APP_CONFIG = window.__APP_CONFIG__ || {};
export const T = APP_CONFIG.translations || {};
export const SIDEBAR_STORAGE_KEY = 'mregister-react-sidebar-collapsed';
export const EMAIL_CREDENTIAL_KINDS = new Set(['gptmail', 'moemail', 'cloudflare_temp_email']);
export const NAV_ITEMS = [
  ['dashboard', 'nav_dashboard'],
  ['credentials', 'nav_credentials'],
  ['proxies', 'nav_proxies'],
  ['create-task', 'nav_create_task'],
  ['task-detail', 'nav_task_detail'],
  ['schedules', 'nav_schedules'],
  ['cpamc', 'cpamc_title'],
  ['api-keys', 'nav_api_keys'],
  ['docs', 'nav_docs'],
];
export const TASK_STATUSES = ['all', 'queued', 'running', 'stopping', 'completed', 'partial', 'failed', 'stopped', 'interrupted'];

export function tr(key, vars = {}) {
  let value = T[key] || key;
  Object.entries(vars).forEach(([name, replacement]) => {
    value = value.replaceAll(`{${name}}`, String(replacement));
  });
  return value;
}

export function statusLabel(status) {
  return T[`status_${status}`] || status;
}

export function isMobileLayout() {
  return window.matchMedia('(max-width: 960px)').matches;
}

export async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });

  if (response.status === 401 || response.status === 403) {
    window.location.reload();
    throw new Error(tr('request_failed'));
  }

  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: tr('request_failed') }));
    throw new Error(data.detail || tr('request_failed'));
  }

  const contentType = response.headers.get('content-type') || '';
  return contentType.includes('application/json') ? response.json() : response;
}

export function parseIntOrNull(value) {
  if (value === '' || value === null || value === undefined) {
    return null;
  }
  return Number(value);
}

export function isEmailCredentialKind(kind) {
  return EMAIL_CREDENTIAL_KINDS.has(kind);
}

export function getPlatformKeys(platforms) {
  return Object.keys(platforms || {});
}

export function initialTaskDraft(platforms) {
  const keys = getPlatformKeys(platforms);
  const platform = keys[0] || 'chatgpt-register-v2';
  return {
    name: '',
    platform,
    quantity: '1',
    concurrency: String(platforms?.[platform]?.default_concurrency || 1),
    email_credential_id: '',
    captcha_credential_id: '',
    proxy_mode: 'none',
    proxy_id: '',
  };
}

export function normalizeTaskDraft(draft, platforms, credentials, proxies) {
  const keys = getPlatformKeys(platforms);
  const platform = platforms[draft.platform] ? draft.platform : (keys[0] || 'chatgpt-register-v2');
  const spec = platforms[platform] || {};
  const mailIds = new Set(credentials.filter((item) => isEmailCredentialKind(item.kind)).map((item) => String(item.id)));
  const captchaIds = new Set(credentials.filter((item) => item.kind === 'yescaptcha').map((item) => String(item.id)));
  const proxyIds = new Set(proxies.map((item) => String(item.id)));
  const next = {
    ...draft,
    platform,
    concurrency: draft.concurrency || String(spec.default_concurrency || 1),
  };

  if (!spec.requires_email_credential) {
    next.email_credential_id = '';
  } else if (!mailIds.has(String(next.email_credential_id || ''))) {
    next.email_credential_id = '';
  }

  if (!spec.requires_captcha_credential) {
    next.captcha_credential_id = '';
  } else if (!captchaIds.has(String(next.captcha_credential_id || ''))) {
    next.captcha_credential_id = '';
  }

  if (!spec.supports_proxy) {
    next.proxy_mode = 'none';
    next.proxy_id = '';
  } else {
    if (!['none', 'default', 'custom'].includes(next.proxy_mode)) {
      next.proxy_mode = 'none';
    }
    if (next.proxy_mode !== 'custom') {
      next.proxy_id = '';
    } else if (!proxyIds.has(String(next.proxy_id || ''))) {
      next.proxy_id = '';
    }
  }

  return next;
}

export function getTaskDisplayName(task) {
  const value = typeof task?.name === 'string' ? task.name.trim() : '';
  const base = value || `#${task?.id ?? ''}`;
  return task?.source === 'schedule' ? `${base} ${tr('schedule_tag_suffix')}` : base;
}
