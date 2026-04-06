/**
 * 通用工具函数
 */

const crypto = require('crypto');
const { URL } = require('url');
const { CHROME_PROFILES, MIN_REGISTRATION_AGE, MAX_REGISTRATION_AGE } = require('./constants');

// ============================================================================
// FlowState
// ============================================================================

class FlowState {
  constructor({ pageType = '', continueUrl = '', method = 'GET', currentUrl = '', source = '', payload = {}, raw = {} } = {}) {
    this.pageType = pageType;
    this.continueUrl = continueUrl;
    this.method = method;
    this.currentUrl = currentUrl;
    this.source = source;
    this.payload = payload;
    this.raw = raw;
  }
}

// ============================================================================
// 随机数据生成
// ============================================================================

function generateDeviceId() {
  return crypto.randomUUID();
}

function generateRandomPassword(length = 16) {
  const upper = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  const lower = 'abcdefghijklmnopqrstuvwxyz';
  const digits = '0123456789';
  const special = '!@#$%';
  const all = upper + lower + digits + special;

  // 保证至少一个各类字符
  let pwd = [
    upper[crypto.randomInt(upper.length)],
    lower[crypto.randomInt(lower.length)],
    digits[crypto.randomInt(digits.length)],
    special[crypto.randomInt(special.length)],
  ];

  for (let i = 4; i < length; i++) {
    pwd.push(all[crypto.randomInt(all.length)]);
  }

  // Fisher-Yates shuffle
  for (let i = pwd.length - 1; i > 0; i--) {
    const j = crypto.randomInt(i + 1);
    [pwd[i], pwd[j]] = [pwd[j], pwd[i]];
  }

  return pwd.join('');
}

function generateRandomName() {
  const { FIRST_NAMES, LAST_NAMES } = require('./constants');
  const first = FIRST_NAMES[crypto.randomInt(FIRST_NAMES.length)];
  const last = LAST_NAMES[crypto.randomInt(LAST_NAMES.length)];
  return [first, last];
}

function generateRandomBirthday() {
  const now = new Date();
  const currentYear = now.getFullYear();
  const year = currentYear - MAX_REGISTRATION_AGE + crypto.randomInt(MAX_REGISTRATION_AGE - MIN_REGISTRATION_AGE + 1);
  const month = crypto.randomInt(1, 13);
  const day = crypto.randomInt(1, 29);
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

// ============================================================================
// PKCE
// ============================================================================

function generatePkce() {
  const codeVerifier = crypto.randomBytes(64).toString('base64url');
  const codeChallenge = crypto.createHash('sha256').update(codeVerifier).digest('base64url');
  return [codeVerifier, codeChallenge];
}

// ============================================================================
// JWT
// ============================================================================

function decodeJwtPayload(token) {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return {};
    let payload = parts[1];
    const pad = (4 - (payload.length % 4)) % 4;
    if (pad) payload += '='.repeat(pad);
    return JSON.parse(Buffer.from(payload, 'base64url').toString('utf-8'));
  } catch {
    return {};
  }
}

// ============================================================================
// URL & Page Type
// ============================================================================

function extractCodeFromUrl(url) {
  if (!url || !url.includes('code=')) return null;
  try {
    const u = new URL(url);
    return u.searchParams.get('code');
  } catch {
    // 可能是部分 URL
    const match = url.match(/[?&]code=([^&#]+)/);
    return match ? match[1] : null;
  }
}

function normalizePageType(value) {
  return String(value || '').trim().toLowerCase().replace(/[-/ ]/g, '_');
}

function normalizeFlowUrl(url, authBase = 'https://auth.openai.com') {
  const value = String(url || '').trim();
  if (!value) return '';
  if (value.startsWith('//')) return `https:${value}`;
  if (value.startsWith('/')) return `${authBase.replace(/\/$/, '')}${value}`;
  return value;
}

function inferPageTypeFromUrl(url) {
  if (!url) return '';
  let parsed;
  try { parsed = new URL(url); } catch { return ''; }

  const host = (parsed.hostname || '').toLowerCase();
  const path = (parsed.pathname || '').toLowerCase();

  if ((parsed.search || '').includes('code=')) return 'oauth_callback';
  if (host.includes('chatgpt.com') && path.includes('/api/auth/callback/')) return 'callback';
  if (path.includes('create-account/password')) return 'create_account_password';
  if (path.includes('email-verification') || path.includes('email-otp')) return 'email_otp_verification';
  if (path.includes('about-you')) return 'about_you';
  if (path.includes('log-in/password')) return 'login_password';
  if (path.includes('sign-in-with-chatgpt') && path.includes('consent')) return 'consent';
  if (path.includes('workspace') && path.includes('select')) return 'workspace_selection';
  if (path.includes('organization') && path.includes('select')) return 'organization_selection';
  if (path.includes('add-phone')) return 'add_phone';
  if (path.includes('callback')) return 'callback';
  if (host.includes('chatgpt.com') && (!path || path === '/')) return 'chatgpt_home';
  if (path) return normalizePageType(path.replace(/^\//, '').replace(/\//g, '_'));
  return '';
}

function extractFlowState(data = null, currentUrl = '', authBase = 'https://auth.openai.com', defaultMethod = 'GET') {
  const raw = (data && typeof data === 'object') ? data : {};
  const page = raw.page || {};
  const payload = page.payload || {};

  const continueUrl = normalizeFlowUrl(
    raw.continue_url || payload.url || '',
    authBase,
  );
  const effectiveCurrentUrl = (raw && continueUrl) ? continueUrl : currentUrl;
  const current = normalizeFlowUrl(effectiveCurrentUrl || continueUrl, authBase);
  const pageType = normalizePageType(page.type) || inferPageTypeFromUrl(continueUrl || current);
  const method = (raw.method || payload.method || defaultMethod || 'GET').toUpperCase();

  return new FlowState({
    pageType,
    continueUrl,
    method,
    currentUrl: current,
    source: raw ? 'api' : 'url',
    payload: typeof payload === 'object' ? payload : {},
    raw,
  });
}

function describeFlowState(state) {
  const target = state.continueUrl || state.currentUrl || '-';
  return `page=${state.pageType || '-'} method=${state.method || '-'} next=${target.slice(0, 80)}...`;
}

// ============================================================================
// Datadog Trace
// ============================================================================

function generateDatadogTrace() {
  const traceHex = crypto.randomBytes(8).toString('hex').padStart(16, '0');
  const parentHex = crypto.randomBytes(8).toString('hex').padStart(16, '0');
  const traceId = BigInt('0x' + traceHex).toString();
  const parentId = BigInt('0x' + parentHex).toString();

  return {
    traceparent: `00-0000000000000000${traceHex}-${parentHex}-01`,
    tracestate: 'dd=s:1;o:rum',
    'x-datadog-origin': 'rum',
    'x-datadog-parent-id': parentId,
    'x-datadog-sampling-priority': '1',
    'x-datadog-trace-id': traceId,
  };
}

// ============================================================================
// Chrome Fingerprint
// ============================================================================

function randomChromeVersion() {
  const profile = CHROME_PROFILES[crypto.randomInt(CHROME_PROFILES.length)];
  const { major, build, patchRange, secChUa } = profile;
  const patch = patchRange[0] + crypto.randomInt(patchRange[1] - patchRange[0] + 1);
  const fullVer = `${major}.0.${build}.${patch}`;
  const ua = `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${fullVer} Safari/537.36`;
  return { major, fullVer, ua, secChUa };
}

// ============================================================================
// Browser Headers (not needed with Playwright, but kept for Sentinel HTTP requests)
// ============================================================================

function buildBrowserHeaders({ url, userAgent, secChUa, accept, referer, origin, contentType, navigation = false, extraHeaders = {} } = {}) {
  const headers = {
    'User-Agent': userAgent || 'Mozilla/5.0',
    'Accept-Language': 'en-US,en;q=0.9',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
  };

  if (accept) headers['Accept'] = accept;
  if (referer) headers['Referer'] = referer;
  if (origin) headers['Origin'] = origin;
  if (contentType) headers['Content-Type'] = contentType;
  if (secChUa) headers['sec-ch-ua'] = secChUa;

  if (navigation) {
    headers['Sec-Fetch-Dest'] = 'document';
    headers['Sec-Fetch-Mode'] = 'navigate';
    headers['Sec-Fetch-User'] = '?1';
    headers['Upgrade-Insecure-Requests'] = '1';
  } else {
    headers['Sec-Fetch-Dest'] = 'empty';
    headers['Sec-Fetch-Mode'] = 'cors';
  }

  Object.entries(extraHeaders).forEach(([k, v]) => {
    if (v != null) headers[k] = v;
  });

  return headers;
}

// ============================================================================
// Utility
// ============================================================================

function randomDelay(low = 300, high = 1000) {
  return new Promise(resolve => setTimeout(resolve, low + crypto.randomInt(high - low)));
}

function seedOaiDeviceCookie(page, deviceId) {
  return page.evaluate((did) => {
    const domains = [
      'chatgpt.com', '.chatgpt.com',
      'openai.com', '.openai.com',
      'auth.openai.com', '.auth.openai.com',
    ];
    // Set cookie via document.cookie for current domain
    document.cookie = `oai-did=${did}; path=/; max-age=31536000; SameSite=Lax`;
  }, deviceId);
}

module.exports = {
  FlowState,
  generateDeviceId,
  generateRandomPassword,
  generateRandomName,
  generateRandomBirthday,
  generatePkce,
  decodeJwtPayload,
  extractCodeFromUrl,
  normalizePageType,
  normalizeFlowUrl,
  inferPageTypeFromUrl,
  extractFlowState,
  describeFlowState,
  generateDatadogTrace,
  randomChromeVersion,
  buildBrowserHeaders,
  randomDelay,
  seedOaiDeviceCookie,
};
