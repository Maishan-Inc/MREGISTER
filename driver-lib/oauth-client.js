/**
 * OAuth 登录客户端 (Phase B)
 * 使用 Playwright 浏览器上下文发起请求
 * 翻译自 Python oauth_client.py
 */

const { URL } = require('url');
const crypto = require('crypto');
const { generatePkce, generateDeviceId, generateDatadogTrace, randomDelay, randomChromeVersion } = require('./utils');
const { buildSentinelToken } = require('./sentinel');
const { OAUTH_CLIENT_ID, OAUTH_REDIRECT_URI, OAUTH_SCOPE } = require('./constants');

const OAUTH_ISSUER = 'https://auth.openai.com';

class OAuthClient {
  constructor(page, config = {}) {
    this.page = page;
    this.config = config;
    this.verbose = config.verbose !== false;
    this.browserMode = config.browserMode || 'headed';
    this.oauthClientId = OAUTH_CLIENT_ID;
    this.oauthRedirectUri = OAUTH_REDIRECT_URI;
    this.lastError = '';
    this.lastWorkspaceId = '';
    this.lastAuthIssue = '';

    // Chrome 指纹
    const chrome = randomChromeVersion();
    this.chromeFull = chrome.fullVer;
    this.secChUa = chrome.secChUa;
    this.ua = chrome.ua;
  }

  _log(msg) {
    if (this.verbose) console.log(`  [OAuth] ${msg}`);
  }

  async _browserPause() {
    if (this.browserMode === 'headed') await randomDelay(120, 400);
  }

  _previewText(value, maxLen = 220) {
    const compact = String(value || '').replace(/\s+/g, ' ').trim();
    if (!compact) return '';
    if (compact.length <= maxLen) return compact;
    return `${compact.slice(0, Math.max(0, maxLen - 3))}...`;
  }

  _readHeader(headers, name) {
    if (!headers || typeof headers !== 'object') return '';
    const lowerName = String(name || '').toLowerCase();
    for (const [key, value] of Object.entries(headers)) {
      if (String(key || '').toLowerCase() === lowerName) return String(value || '');
    }
    return '';
  }

  _hasCloudflareMarker(value) {
    return /cloudflare|cf-ray|cdn-cgi|challenge-platform|attention required|just a moment|checking your browser|security check/i.test(
      String(value || ''),
    );
  }

  _classifyOAuthIssue(snapshot = {}) {
    const status = Number(snapshot.status || 0);
    const server = this._readHeader(snapshot.headers, 'server');
    const location = this._readHeader(snapshot.headers, 'location');
    const combined = [
      snapshot.url,
      location,
      server,
      snapshot.text,
      snapshot.errorMessage,
    ].filter(Boolean).join('\n');

    if (
      this._hasCloudflareMarker(combined) ||
      ((status === 403 || status === 503) && /cloudflare/i.test(server))
    ) {
      return '疑似 CF 盾 / Cloudflare 挑战或拦截';
    }

    if (
      status === 0 ||
      /failed to fetch|fetch timeout|timed out|timeout|abort|aborted|networkerror|socket|econn|enet|tls|ssl/i.test(combined)
    ) {
      return '疑似网络波动、请求超时或连接异常';
    }

    if ([502, 503, 504, 520, 522, 524, 525, 526].includes(status)) {
      return '疑似网络波动或上游网关抖动';
    }

    if (status === 429) {
      return '接口限流，更像风控或频率问题，不像纯网络波动';
    }

    if (status === 400 || status === 401) {
      return '更像 OAuth code / 会话状态失效，不像网络或 CF';
    }

    if (status === 403) {
      return '请求被拒绝，可能是 CF 盾或风控';
    }

    return '原因未明，更像会话链路或业务状态问题';
  }

  _formatOAuthIssue(stage, snapshot = {}, extra = '') {
    const parts = [
      `${stage}: ${this._classifyOAuthIssue(snapshot)}`,
      `status=${Number(snapshot.status || 0)}`,
      `url=${this._previewText(snapshot.url || '', 140) || '-'}`,
    ];

    const location = this._previewText(this._readHeader(snapshot.headers, 'location'), 140);
    if (location) parts.push(`location=${location}`);

    const server = this._previewText(this._readHeader(snapshot.headers, 'server'), 60);
    if (server) parts.push(`server=${server}`);

    const body = this._previewText(snapshot.text || snapshot.errorMessage || '', 180);
    if (body) parts.push(`body=${body}`);

    if (extra) parts.push(extra);
    return parts.join(' | ');
  }

  _rememberOAuthIssue(stage, snapshot = {}, extra = '') {
    const message = this._formatOAuthIssue(stage, snapshot, extra);
    this.lastAuthIssue = message;
    this._log(message);
    return message;
  }

  _snapshotFetchResult(result = {}) {
    return {
      status: Number(result.status || 0),
      url: result.url || '',
      headers: result.headers || {},
      text: result.text || '',
      errorMessage: result.errorMessage || '',
    };
  }

  async _snapshotApiResponse(response) {
    if (!response) {
      return { status: 0, url: '', headers: {}, text: '', errorMessage: 'empty response' };
    }

    let text = '';
    try {
      text = await response.text();
    } catch {}

    return {
      status: typeof response.status === 'function' ? response.status() : 0,
      url: typeof response.url === 'function' ? response.url() : '',
      headers: typeof response.headers === 'function' ? response.headers() : {},
      text,
      errorMessage: '',
    };
  }

  _buildErrorSnapshot(url, error) {
    return {
      status: 0,
      url: url || '',
      headers: {},
      text: '',
      errorMessage: error?.message || String(error || ''),
    };
  }

  _getOAuthNetworkRetryAttempts() {
    const configured = Number(this.config.oauthNetworkRetryAttempts || 3);
    if (!Number.isFinite(configured)) return 3;
    return Math.max(1, Math.min(5, Math.trunc(configured)));
  }

  _getOAuthNetworkRetryDelayRange() {
    const min = Number(this.config.oauthNetworkRetryDelayMinMs || 1200);
    const max = Number(this.config.oauthNetworkRetryDelayMaxMs || 2800);
    if (!Number.isFinite(min) || !Number.isFinite(max)) return { min: 1200, max: 2800 };
    return {
      min: Math.max(200, Math.min(min, max)),
      max: Math.max(Math.max(200, min), max),
    };
  }

  _isRetryableNetworkIssue(snapshot = {}) {
    const status = Number(snapshot.status || 0);
    const combined = [
      snapshot.url,
      this._readHeader(snapshot.headers, 'location'),
      this._readHeader(snapshot.headers, 'server'),
      snapshot.text,
      snapshot.errorMessage,
    ].filter(Boolean).join('\n');

    if ([0, 408, 425, 502, 503, 504, 520, 522, 524, 525, 526].includes(status)) {
      return true;
    }

    return /failed to fetch|fetch timeout|timed out|timeout|abort|aborted|networkerror|socket|econn|enet|tls|ssl|temporarily unavailable|connection reset/i.test(
      combined,
    );
  }

  async _waitForOAuthNetworkRetry(stage, attempt, maxAttempts, snapshot = {}, extra = '') {
    const nextAttempt = Math.min(attempt + 1, maxAttempts);
    const message = this._formatOAuthIssue(
      `${stage}: 检测到疑似网络波动，准备第 ${nextAttempt}/${maxAttempts} 次尝试`,
      snapshot,
      extra,
    );
    this.lastAuthIssue = message;
    this._log(message);
    const { min, max } = this._getOAuthNetworkRetryDelayRange();
    await randomDelay(min, max);
  }

  async _fetchWithNetworkRetry(url, options, stage, extra = '') {
    const maxAttempts = this._getOAuthNetworkRetryAttempts();
    let lastResult = null;

    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      const result = await this._fetch(url, options);
      lastResult = result;
      const snapshot = this._snapshotFetchResult(result);

      if (result.ok) {
        if (attempt > 1) {
          this._log(`${stage}: 网络重试后恢复，status=${result.status}`);
        }
        return result;
      }

      if (attempt < maxAttempts && this._isRetryableNetworkIssue(snapshot)) {
        await this._waitForOAuthNetworkRetry(stage, attempt, maxAttempts, snapshot, extra);
        continue;
      }

      return result;
    }

    return lastResult;
  }

  async _requestContextGetWithNetworkRetry(requestContext, url, options, stage, extra = '') {
    const maxAttempts = this._getOAuthNetworkRetryAttempts();
    let lastSnapshot = this._buildErrorSnapshot(url, 'request not started');

    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        const response = await requestContext.get(url, options);
        const snapshot = await this._snapshotApiResponse(response);
        lastSnapshot = snapshot;

        if (attempt < maxAttempts && this._isRetryableNetworkIssue(snapshot)) {
          await this._waitForOAuthNetworkRetry(stage, attempt, maxAttempts, snapshot, extra);
          continue;
        }

        if (attempt > 1 && response.ok()) {
          this._log(`${stage}: 网络重试后恢复，status=${snapshot.status}`);
        }

        return { response, snapshot, error: null };
      } catch (error) {
        const snapshot = this._buildErrorSnapshot(url, error);
        lastSnapshot = snapshot;

        if (attempt < maxAttempts && this._isRetryableNetworkIssue(snapshot)) {
          await this._waitForOAuthNetworkRetry(stage, attempt, maxAttempts, snapshot, extra);
          continue;
        }

        return { response: null, snapshot, error };
      }
    }

    return { response: null, snapshot: lastSnapshot, error: null };
  }

  /**
   * 在浏览器页面上下文中执行 fetch
   */
  async _fetch(url, options = {}) {
    const { method = 'GET', headers = {}, body = null, redirect = 'manual', timeoutMs } = options;
    const effectiveTimeoutMs = Math.max(1000, Number(timeoutMs || this.config.fetchTimeoutMs || 30000));
    return this.page.evaluate(async ({ url, method, headers, body, redirect, timeoutMs }) => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(new Error(`fetch timeout after ${timeoutMs}ms`)), timeoutMs);
      try {
        const opts = { method, headers, redirect, signal: controller.signal };
        if (body !== null) opts.body = body;
        const resp = await fetch(url, opts);
        const respHeaders = {};
        resp.headers.forEach((v, k) => { respHeaders[k] = v; });
        let text;
        try { text = await resp.text(); } catch { text = ''; }
        let data;
        try { data = JSON.parse(text); } catch { data = null; }
        return { status: resp.status, headers: respHeaders, data, url: resp.url || url, text, type: resp.type, ok: resp.ok, redirected: resp.redirected };
      } catch (e) {
        return { status: 0, headers: {}, data: null, url, text: e.message, type: 'error', ok: false, redirected: false, errorMessage: e.message };
      } finally {
        clearTimeout(timer);
      }
    }, { url, method, headers, body, redirect, timeoutMs: effectiveTimeoutMs });
  }

  // ========================================================================
  // 状态推断
  // ========================================================================

  _extractFlowState(data, currentUrl = '') {
    const raw = (data && typeof data === 'object') ? data : {};
    const page = raw.page || {};
    const payload = page.payload || {};
    const continueUrl = raw.continue_url || payload.url || '';
    const effectiveUrl = continueUrl || currentUrl;
    const pageType = this._inferPageType(data, effectiveUrl);
    const method = (raw.method || payload.method || 'GET').toUpperCase();
    return { pageType, continueUrl, method, currentUrl: effectiveUrl, payload: payload || {}, raw };
  }

  _inferPageType(data, currentUrl = '') {
    const raw = (data && typeof data === 'object') ? data : {};
    const pt = (raw.page?.type || '').toLowerCase().replace(/[-/ ]/g, '_');
    if (pt) return pt;

    const url = (currentUrl || '').toLowerCase();
    if (!url) return '';
    if (url.includes('code=')) return 'oauth_callback';
    if (url.includes('create-account/password')) return 'create_account_password';
    if (url.includes('email-verification') || url.includes('email-otp')) return 'email_otp_verification';
    if (url.includes('about-you')) return 'about_you';
    if (url.includes('log-in/password')) return 'login_password';
    if (url.includes('add-phone')) return 'add_phone';
    if (url.includes('sign-in-with-chatgpt') && url.includes('consent')) return 'consent';
    if (url.includes('workspace') && url.includes('select')) return 'workspace_selection';
    if (url.includes('organization') && url.includes('select')) return 'organization_selection';
    if (url.includes('/api/oauth/oauth2/auth')) return 'external_url';
    if (url.includes('callback')) return 'callback';
    return '';
  }

  _extractCodeFromUrl(url) {
    if (!url || !url.includes('code=')) return null;
    try { return new URL(url).searchParams.get('code'); } catch {}
    const m = url.match(/[?&]code=([^&#]+)/);
    return m ? m[1] : null;
  }

  _normalizeUrl(targetUrl, baseUrl = OAUTH_ISSUER) {
    const value = String(targetUrl || '').trim();
    if (!value) return '';
    if (/^https?:\/\//i.test(value)) return value;
    try {
      return new URL(value, baseUrl).toString();
    } catch {
      return value;
    }
  }

  _extractCodeFromError(error) {
    const message = error?.message || String(error || '');
    const localhostMatch = message.match(/(https?:\/\/localhost[^\s'"]+)/);
    if (!localhostMatch) return null;

    const callbackUrl = localhostMatch[1];
    const code = this._extractCodeFromUrl(callbackUrl);
    if (!code) return null;
    return { code, callbackUrl };
  }

  _buildFollowHeaders(referer) {
    const headers = {
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      'Upgrade-Insecure-Requests': '1',
      'User-Agent': this.ua,
    };
    const refererUrl = this._normalizeUrl(referer);
    if (refererUrl) headers.Referer = refererUrl;
    return headers;
  }

  async _followUrlForCode(startUrl, referer, maxHops = 16) {
    const requestContext = this.page.context().request;
    const headers = this._buildFollowHeaders(referer);
    let currentUrl = this._normalizeUrl(startUrl);
    let lastUrl = currentUrl;

    for (let hop = 0; hop < maxHops; hop += 1) {
      const initialCode = this._extractCodeFromUrl(currentUrl);
      if (initialCode) return { code: initialCode, finalUrl: currentUrl };

      const requestResult = await this._requestContextGetWithNetworkRetry(
        requestContext,
        currentUrl,
        {
          headers,
          timeout: 30000,
          maxRedirects: 0,
          failOnStatusCode: false,
        },
        `redirect-follow[${hop + 1}]`,
        `start=${this._previewText(startUrl, 120)}`,
      );
      const { response, snapshot, error } = requestResult;

      if (error) {
        const extracted = this._extractCodeFromError(error);
        if (extracted) {
          this._log(`redirect-follow[${hop + 1}] hit localhost callback`);
          return { code: extracted.code, finalUrl: extracted.callbackUrl };
        }
        const issue = this._rememberOAuthIssue(
          `redirect-follow[${hop + 1}] 请求异常`,
          snapshot,
        );
        return { code: null, finalUrl: lastUrl, issue };
      }

      lastUrl = (response?.url() || snapshot.url || currentUrl);
      const status = Number(snapshot.status || 0);
      this._log(`redirect-follow[${hop + 1}] ${status} ${(lastUrl || '-').slice(0, 140)}`);

      const directCode = this._extractCodeFromUrl(lastUrl);
      if (directCode) return { code: directCode, finalUrl: lastUrl };

      const responseHeaders = response ? response.headers() : {};
      const locationRaw = responseHeaders.location || responseHeaders.Location || '';
      if (locationRaw) {
        const location = this._normalizeUrl(locationRaw, lastUrl);
        const locationCode = this._extractCodeFromUrl(location);
        if (locationCode) return { code: locationCode, finalUrl: location };

        if ([301, 302, 303, 307, 308].includes(status)) {
          currentUrl = location;
          headers.Referer = lastUrl;
          continue;
        }
      }

      const issue = this._rememberOAuthIssue(
        `redirect-follow[${hop + 1}] 未拿到 authorization code`,
        snapshot,
      );
      return { code: null, finalUrl: lastUrl, issue };
    }

    const issue = this._rememberOAuthIssue(
      'redirect-follow 超出最大跳转次数',
      { status: 0, url: lastUrl, headers: {}, text: '', errorMessage: `max_hops=${maxHops}` },
    );
    return { code: null, finalUrl: lastUrl, issue };
  }

  async _allowRedirectExtractCode(targetUrl, referer) {
    const requestContext = this.page.context().request;
    const normalizedUrl = this._normalizeUrl(targetUrl);
    if (!normalizedUrl) return { code: null, finalUrl: normalizedUrl };

    const requestResult = await this._requestContextGetWithNetworkRetry(
      requestContext,
      normalizedUrl,
      {
        headers: this._buildFollowHeaders(referer),
        timeout: 30000,
        failOnStatusCode: false,
      },
      'allow-redirect',
      `start=${this._previewText(targetUrl, 120)}`,
    );
    const { response, snapshot, error } = requestResult;

    if (error) {
      const extracted = this._extractCodeFromError(error);
      if (extracted) {
        this._log('allow-redirect extracted code from localhost callback');
        return { code: extracted.code, finalUrl: extracted.callbackUrl };
      }
      const issue = this._rememberOAuthIssue(
        'allow-redirect 请求异常',
        snapshot,
      );
      return { code: null, finalUrl: normalizedUrl, issue };
    }

    const finalUrl = (response?.url() || snapshot.url || normalizedUrl);
    const code = this._extractCodeFromUrl(finalUrl);
    if (code) {
      this._log('allow-redirect hit final URL code');
      return { code, finalUrl };
    }

    const responseHeaders = response ? response.headers() : {};
    const locationRaw = responseHeaders.location || responseHeaders.Location || '';
    if (locationRaw) {
      const location = this._normalizeUrl(locationRaw, finalUrl);
      const locationCode = this._extractCodeFromUrl(location);
      if (locationCode) {
        this._log('allow-redirect hit Location code');
        return { code: locationCode, finalUrl: location };
      }
    }

    const issue = this._rememberOAuthIssue(
      'allow-redirect 未拿到 authorization code',
      snapshot,
    );
    return { code: null, finalUrl, issue };
  }

  _extractCodeFromState(state) {
    for (const candidate of [state.continueUrl, state.currentUrl, (state.payload || {}).url]) {
      const code = this._extractCodeFromUrl(candidate);
      if (code) return code;
    }
    return null;
  }

  _isLoginPassword(state) { return state.pageType === 'login_password'; }
  _isCreateAccountPassword(state) {
    const target = `${state.continueUrl} ${state.currentUrl}`.toLowerCase();
    return state.pageType === 'create_account_password' || target.includes('create-account/password');
  }
  _isEmailOtp(state) {
    const target = `${state.continueUrl} ${state.currentUrl}`.toLowerCase();
    return state.pageType === 'email_otp_verification' || target.includes('email-verification') || target.includes('email-otp');
  }
  _isAboutYou(state) {
    const target = `${state.continueUrl} ${state.currentUrl}`.toLowerCase();
    return state.pageType === 'about_you' || target.includes('about-you');
  }
  _isAddPhone(state) {
    const target = `${state.continueUrl} ${state.currentUrl}`.toLowerCase();
    return state.pageType === 'add_phone' || target.includes('add-phone');
  }
  _requiresNavigation(state) {
    if ((state.method || 'GET').toUpperCase() !== 'GET') return false;
    if (state.pageType === 'external_url' && state.continueUrl) return true;
    if (state.continueUrl && state.continueUrl !== state.currentUrl) return true;
    return false;
  }

  _canContinueFromBootstrappedState(state) {
    if (!state) return false;
    if (this._extractCodeFromState(state)) return true;

    const target = `${state.continueUrl || ''} ${state.currentUrl || ''}`.toLowerCase();
    return (
      [
        'login_password',
        'create_account_password',
        'email_otp_verification',
        'about_you',
        'add_phone',
        'consent',
        'workspace_selection',
        'organization_selection',
        'callback',
        'oauth_callback',
      ].includes(state.pageType) ||
      target.includes('consent') ||
      target.includes('workspace') ||
      target.includes('organization') ||
      target.includes('about-you') ||
      target.includes('add-phone') ||
      target.includes('email-verification') ||
      target.includes('email-otp') ||
      target.includes('log-in/password') ||
      target.includes('create-account/password') ||
      target.includes('callback')
    );
  }

  // ========================================================================
  // OAuth 操作方法
  // ========================================================================

  /**
   * Bootstrap OAuth session - GET /oauth/authorize with PKCE
   */
  async _bootstrapOAuthSession(authorizeUrl, authorizeParams, deviceId) {
    // Seed oai-did cookies
    await this.page.context().addCookies([
      { name: 'oai-did', value: deviceId, domain: 'auth.openai.com', path: '/' },
      { name: 'oai-did', value: deviceId, domain: '.auth.openai.com', path: '/' },
      { name: 'oai-did', value: deviceId, domain: 'openai.com', path: '/' },
    ]);

    const fullUrl = `${authorizeUrl}?${new URLSearchParams(authorizeParams).toString()}`;
    this._log('Bootstrap OAuth session...');

    try {
      await this._browserPause();
      await this.page.goto(fullUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
      const finalUrl = this.page.url();
      this._log(`/oauth/authorize -> ${finalUrl.slice(0, 120)}`);

      // 检查 login_session cookie
      const cookies = await this.page.context().cookies(['https://auth.openai.com']);
      const hasLoginSession = cookies.some(c => c.name === 'login_session');
      this._log(`login_session: ${hasLoginSession ? '已获取' : '未获取'}`);

      if (hasLoginSession) return finalUrl;
    } catch (e) {
      this._log(`/oauth/authorize 异常: ${e.message}`);
    }

    // Fallback: /api/oauth/oauth2/auth
    this._log('尝试 /api/oauth/oauth2/auth...');
    try {
      const fallbackUrl = `${OAUTH_ISSUER}/api/oauth/oauth2/auth?${new URLSearchParams(authorizeParams).toString()}`;
      await this._browserPause();
      await this.page.goto(fallbackUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
      const finalUrl = this.page.url();
      this._log(`/api/oauth/oauth2/auth -> ${finalUrl.slice(0, 120)}`);
      return finalUrl;
    } catch (e) {
      this._log(`/api/oauth/oauth2/auth 异常: ${e.message}`);
    }

    return '';
  }

  /**
   * 提交邮箱 authorize/continue
   */
  async _submitAuthorizeContinue(email, deviceId, referer) {
    this._log('步骤2: POST /api/accounts/authorize/continue');
    const sentinelToken = await buildSentinelToken(deviceId, 'authorize_continue', this.ua, this.secChUa, this.page);

    const headers = {
      'Accept': 'application/json',
      'Referer': referer,
      'Origin': OAUTH_ISSUER,
      'Content-Type': 'application/json',
      'Sec-Fetch-Site': 'same-origin',
      'oai-device-id': deviceId,
      ...generateDatadogTrace(),
    };
    if (sentinelToken) headers['openai-sentinel-token'] = sentinelToken;

    await this._browserPause();
    const result = await this._fetch(`${OAUTH_ISSUER}/api/accounts/authorize/continue`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ username: { kind: 'email', value: email }, screen_hint: 'login' }),
    });

    if (result.status === 429) {
      this._log('authorize_continue: 429 限流，等待后重试');
      await randomDelay(2000, 4500);
      // Retry once
      return this._submitAuthorizeContinue(email, deviceId, referer);
    }

    if (!result.ok) {
      this._log(`提交邮箱失败: ${result.status} - ${(result.text || '').slice(0, 180)}`);
      return null;
    }

    const flowState = this._extractFlowState(result.data, result.url);
    this._log(`authorize_continue -> page=${flowState.pageType}`);
    return flowState;
  }

  /**
   * 提交密码验证
   */
  async _submitPasswordVerify(password, deviceId, referer) {
    this._log('步骤3: POST /api/accounts/password/verify');
    const sentinelToken = await buildSentinelToken(deviceId, 'password_verify', this.ua, this.secChUa, this.page);
    this._log(`sentinel token: ${sentinelToken ? '已获取 (' + sentinelToken.slice(0, 30) + '...)' : '未获取！'}`);

    const headers = {
      'Accept': 'application/json',
      'Referer': referer || `${OAUTH_ISSUER}/log-in/password`,
      'Origin': OAUTH_ISSUER,
      'Content-Type': 'application/json',
      'Sec-Fetch-Site': 'same-origin',
      'oai-device-id': deviceId,
      ...generateDatadogTrace(),
    };
    if (sentinelToken) headers['openai-sentinel-token'] = sentinelToken;

    await this._browserPause();
    const result = await this._fetch(`${OAUTH_ISSUER}/api/accounts/password/verify`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ password }),
    });

    if (result.status === 429) {
      this._log('password_verify: 429 限流，等待后重试');
      await randomDelay(2000, 4500);
    }

    if (!result.ok) {
      this._log(`密码验证失败: ${result.status} - ${(result.text || '').slice(0, 180)}`);
      return null;
    }

    return this._extractFlowState(result.data, result.url);
  }

  /**
   * 提交 about_you (姓名 + 生日)
   */
  async _submitAboutYou(firstName, lastName, birthdate, deviceId, referer) {
    this._log('步骤5: 命中 about_you，提交姓名和生日');
    const fullName = `${firstName} ${lastName}`.trim();
    if (!fullName || !birthdate) {
      this._log('about_you 资料不完整');
      return null;
    }

    const sentinelToken = await buildSentinelToken(deviceId, 'oauth_create_account', this.ua, this.secChUa, this.page);
    if (!sentinelToken) {
      this._log('无法获取 sentinel token (oauth_create_account)');
      return null;
    }

    const headers = {
      'Accept': 'application/json',
      'Referer': referer || `${OAUTH_ISSUER}/about-you`,
      'Origin': OAUTH_ISSUER,
      'Content-Type': 'application/json',
      'Sec-Fetch-Site': 'same-origin',
      'oai-device-id': deviceId,
      'openai-sentinel-token': sentinelToken,
      ...generateDatadogTrace(),
    };

    await this._browserPause();
    const result = await this._fetch(`${OAUTH_ISSUER}/api/accounts/create_account`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ name: fullName, birthdate }),
    });

    if (!result.ok) {
      const errorCode =
        result.data?.error?.code ||
        result.data?.error?.type ||
        result.data?.code ||
        '';
      const errorMessage =
        result.data?.error?.message ||
        result.text ||
        '';

      if (
        result.status === 400 &&
        (
          String(errorCode).toLowerCase().includes('user_already_exists') ||
          String(errorMessage).toLowerCase().includes('already exists for this email address')
        )
      ) {
        const fallbackConsentUrl = `${OAUTH_ISSUER}/sign-in-with-chatgpt/codex/consent`;
        this._log('about_you 返回 user_already_exists，按已建号处理并回退到 consent');
        return this._extractFlowState(null, fallbackConsentUrl);
      }
      this._log(`about_you 提交失败: ${result.status} - ${(result.text || '').slice(0, 180)}`);
      return null;
    }

    const flowState = this._extractFlowState(result.data, result.url);
    this._log(`about_you 提交成功 page=${flowState.pageType}`);
    return flowState;
  }

  /**
   * 跟随 continue_url 导航
   */
  async _followFlowState(state, referer) {
    const targetUrl = this._normalizeUrl(state.continueUrl || state.currentUrl, state.currentUrl || OAUTH_ISSUER);
    if (!targetUrl) return { code: null, state };

    // 先检查 URL 中是否有 code
    const initialCode = this._extractCodeFromUrl(targetUrl);
    if (initialCode) return { code: initialCode, state: this._extractFlowState(null, targetUrl) };

    const isOAuthRedirectBootstrap =
      state.pageType === 'external_url' ||
      targetUrl.includes('/api/oauth/oauth2/auth');

    if (isOAuthRedirectBootstrap) {
      const followResult = await this._followUrlForCode(targetUrl, referer);
      if (followResult.code) {
        return { code: followResult.code, state: this._extractFlowState(null, followResult.finalUrl || targetUrl) };
      }

      const allowRedirectResult = await this._allowRedirectExtractCode(targetUrl, referer);
      if (allowRedirectResult.code) {
        return {
          code: allowRedirectResult.code,
          state: this._extractFlowState(null, allowRedirectResult.finalUrl || targetUrl),
        };
      }

      const redirectFinalUrl = allowRedirectResult.finalUrl || followResult.finalUrl || targetUrl;
      return {
        code: null,
        state: this._extractFlowState(null, redirectFinalUrl),
        issue: allowRedirectResult.issue || followResult.issue || '',
      };
    }

    try {
      const maxAttempts = this._getOAuthNetworkRetryAttempts();
      let finalUrl = '';
      let gotoError = null;

      for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
        try {
          await this._browserPause();
          await this.page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
          finalUrl = this.page.url();
          gotoError = null;
          if (attempt > 1) {
            this._log(`followFlowState: 网络重试后恢复，url=${this._previewText(finalUrl, 120)}`);
          }
          break;
        } catch (error) {
          gotoError = error;
          const snapshot = this._buildErrorSnapshot(targetUrl, error);
          if (attempt < maxAttempts && this._isRetryableNetworkIssue(snapshot)) {
            await this._waitForOAuthNetworkRetry('followFlowState 导航', attempt, maxAttempts, snapshot);
            continue;
          }
          throw error;
        }
      }

      if (gotoError) throw gotoError;

      const code = this._extractCodeFromUrl(finalUrl);
      if (code) return { code, state: this._extractFlowState(null, finalUrl) };

      return { code: null, state: this._extractFlowState(null, finalUrl) };
    } catch (e) {
      // 尝试从异常中提取 localhost URL
      const extracted = this._extractCodeFromError(e);
      if (extracted) {
        return { code: extracted.code, state: this._extractFlowState(null, extracted.callbackUrl) };
      }
      const issue = this._rememberOAuthIssue(
        'followFlowState 导航异常',
        { status: 0, url: targetUrl, headers: {}, text: '', errorMessage: e.message || String(e) },
      );
      return { code: null, state, issue };
    }
  }

  /**
   * workspace/org 选择
   */
  async _submitWorkspaceAndOrg(consentUrl, deviceId) {
    // 尝试从 cookie 解码 session 数据
    let sessionData = await this._decodeOAuthSessionCookie();

    if (!sessionData || !sessionData.workspaces?.length) {
      // 尝试从 consent 页面 HTML 提取
      sessionData = await this._extractWorkspaceFromConsentPage(consentUrl);
    }

    if (!sessionData?.workspaces?.length) {
      const issue = this._rememberOAuthIssue(
        'workspace 解析失败',
        { status: 0, url: consentUrl, headers: {}, text: '', errorMessage: 'missing workspace metadata' },
      );
      return { code: null, state: null, issue };
    }

    const workspaceId = sessionData.workspaces[0]?.id;
    if (!workspaceId) {
      const issue = this._rememberOAuthIssue(
        'workspace 解析失败',
        { status: 0, url: consentUrl, headers: {}, text: '', errorMessage: 'workspace id missing' },
      );
      return { code: null, state: null, issue };
    }

    this.lastWorkspaceId = workspaceId;
    this._log(`选择 workspace: ${workspaceId}`);

    // POST workspace/select
    const headers = {
      'Accept': 'application/json',
      'Referer': consentUrl,
      'Origin': OAUTH_ISSUER,
      'Content-Type': 'application/json',
      'Sec-Fetch-Site': 'same-origin',
      'oai-device-id': deviceId,
      ...generateDatadogTrace(),
    };

    const effectiveWorkspaceResult = await this._fetchWithNetworkRetry(
      `${OAUTH_ISSUER}/api/accounts/workspace/select`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify({ workspace_id: workspaceId }),
      },
      'workspace/select',
      `workspace=${workspaceId}`,
    );
    this._log(`workspace/select -> ${effectiveWorkspaceResult.status}`);

    if (!effectiveWorkspaceResult.ok) {
      const issue = this._rememberOAuthIssue(
        'workspace/select 失败',
        this._snapshotFetchResult(effectiveWorkspaceResult),
        `workspace=${workspaceId}`,
      );
      return { code: null, state: null, issue };
    }

    // 检查重定向中的 code
    const location = effectiveWorkspaceResult.headers?.location || '';
    if (location) {
      const resolvedLocation = this._normalizeUrl(location, consentUrl);
      const code = this._extractCodeFromUrl(resolvedLocation);
      if (code) return { code, state: this._extractFlowState(null, resolvedLocation) };

      const followResult = await this._followUrlForCode(resolvedLocation, consentUrl);
      if (followResult.code) {
        return { code: followResult.code, state: this._extractFlowState(null, followResult.finalUrl || resolvedLocation) };
      }

      return {
        code: null,
        state: this._extractFlowState(null, resolvedLocation),
        issue: followResult.issue || '',
      };
    }

    if (effectiveWorkspaceResult.ok && effectiveWorkspaceResult.data) {
      const flowState = this._extractFlowState(effectiveWorkspaceResult.data, effectiveWorkspaceResult.url);
      const orgs = effectiveWorkspaceResult.data?.data?.orgs || [];

      if (orgs.length > 0 && orgs[0]?.id) {
        this._log(`选择 organization: ${orgs[0].id}`);
        const orgBody = { org_id: orgs[0].id };
        if (orgs[0].projects?.[0]?.id) orgBody.project_id = orgs[0].projects[0].id;

        const orgResult = await this._fetchWithNetworkRetry(
          `${OAUTH_ISSUER}/api/accounts/organization/select`,
          {
            method: 'POST',
            headers,
            body: JSON.stringify(orgBody),
          },
          'organization/select',
          `workspace=${workspaceId}; org=${orgs[0].id}`,
        );
        this._log(`organization/select -> ${orgResult.status}`);

        if (!orgResult.ok) {
          const issue = this._rememberOAuthIssue(
            'organization/select 失败',
            this._snapshotFetchResult(orgResult),
            `workspace=${workspaceId}; org=${orgs[0].id}`,
          );
          return { code: null, state: null, issue };
        }

        const orgLocation = orgResult.headers?.location || '';
        if (orgLocation) {
          const resolvedOrgLocation = this._normalizeUrl(orgLocation, consentUrl);
          const code = this._extractCodeFromUrl(resolvedOrgLocation);
          if (code) return { code, state: this._extractFlowState(null, resolvedOrgLocation) };

          const followResult = await this._followUrlForCode(
            resolvedOrgLocation,
            flowState.continueUrl || consentUrl,
          );
          if (followResult.code) {
            return {
              code: followResult.code,
              state: this._extractFlowState(null, followResult.finalUrl || resolvedOrgLocation),
            };
          }

          return {
            code: null,
            state: this._extractFlowState(null, resolvedOrgLocation),
            issue: followResult.issue || '',
          };
        }

        if (orgResult.ok && orgResult.data) {
          const orgState = this._extractFlowState(orgResult.data, orgResult.url);
          const code = this._extractCodeFromState(orgState);
          if (code) return { code, state: orgState };

          if (orgState.continueUrl) {
            const followed = await this._followFlowState(
              orgState,
              flowState.continueUrl || consentUrl,
            );
            if (followed.code || followed.state) return followed;
            return { code: null, state: null, issue: followed.issue || '' };
          }

          return { code: null, state: orgState, issue: '' };
        }
      }

      // 跟随 continue_url
      if (flowState.continueUrl) {
        return this._followFlowState(flowState, consentUrl);
      }

      return { code: null, state: flowState, issue: '' };
    }

    const issue = this._rememberOAuthIssue(
      'workspace/select 未返回可继续状态',
      this._snapshotFetchResult(effectiveWorkspaceResult),
      `workspace=${workspaceId}`,
    );
    return { code: null, state: null, issue };
  }

  async _decodeOAuthSessionCookie() {
    try {
      const cookies = await this.page.context().cookies(['https://auth.openai.com']);
      const sessionCookie = cookies.find(c => c.name === 'oai-client-auth-session');
      if (!sessionCookie) return null;

      let value = sessionCookie.value;
      if (value.includes('.')) value = value.split('.')[0];

      const padded = value + '='.repeat((-value.length) % 4);
      for (const decode of [Buffer.from.bind(Buffer)]) {
        try {
          const decoded = decode(padded, 'base64url').toString('utf-8');
          const parsed = JSON.parse(decoded);
          if (typeof parsed === 'object') return parsed;
        } catch {}
        try {
          const decoded = decode(padded, 'base64').toString('utf-8');
          const parsed = JSON.parse(decoded);
          if (typeof parsed === 'object') return parsed;
        } catch {}
      }
    } catch {}
    return null;
  }

  async _extractWorkspaceFromConsentPage(consentUrl) {
    try {
      await this._browserPause();
      const response = await this.page.goto(consentUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
      const html = await this.page.content();
      if (!html || !html.includes('workspaces')) return null;

      // 从 React Router stream 中提取 workspace 数据
      const ids = [...html.matchAll(/"id"(?:,|:)"([0-9a-f-]{36})"/gi)].map(m => m[1]);
      const kinds = [...html.matchAll(/"kind"(?:,|:)"([^"]+)"/gi)].map(m => m[1]);

      if (!ids.length) return null;

      const seen = new Set();
      const workspaces = [];
      ids.forEach((id, i) => {
        if (seen.has(id)) return;
        seen.add(id);
        const item = { id };
        if (i < kinds.length) item.kind = kinds[i];
        workspaces.push(item);
      });

      return workspaces.length ? { workspaces } : null;
    } catch {}
    return null;
  }

  /**
   * 用 authorization code 换取 tokens
   */
  async _exchangeCodeForTokens(code, codeVerifier) {
    this._log('步骤7: POST /oauth/token');

    const result = await this._fetchWithNetworkRetry(
      `${OAUTH_ISSUER}/oauth/token`,
      {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Referer': `${OAUTH_ISSUER}/sign-in-with-chatgpt/codex/consent`,
          'Origin': OAUTH_ISSUER,
          'Content-Type': 'application/x-www-form-urlencoded',
          'Sec-Fetch-Site': 'same-origin',
        },
        body: new URLSearchParams({
          grant_type: 'authorization_code',
          code,
          redirect_uri: this.oauthRedirectUri,
          client_id: this.oauthClientId,
          code_verifier: codeVerifier,
        }).toString(),
        redirect: 'follow',
      },
      'oauth/token',
      `workspace=${this.lastWorkspaceId || '-'}`,
    );

    if (result.ok && result.data) {
      return result.data;
    }
    this._rememberOAuthIssue(
      'oauth/token 失败',
      this._snapshotFetchResult(result),
      `workspace=${this.lastWorkspaceId || '-'}`,
    );
    return null;
  }

  // ========================================================================
  // OAuth OTP 处理
  // ========================================================================

  async _sendEmailOtp(deviceId, referer) {
    this._log('触发 OAuth 邮箱 OTP 发送');
    const result = await this._fetch(`${OAUTH_ISSUER}/api/accounts/email-otp/send`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json, text/plain, */*',
        'Referer': referer || `${OAUTH_ISSUER}/email-verification`,
        'Sec-Fetch-Site': 'same-origin',
        'oai-device-id': deviceId,
      },
      redirect: 'follow',
    });

    this._log(`email-otp/send -> ${result.status}`);
    return result.status === 200;
  }

  async _handleOtpVerification(email, deviceId, mailbox, state, options = {}) {
    this._log('步骤4: 检测到邮箱 OTP 验证');

    const {
      proactivelySendOtp = false,
    } = options;

    const sentinelToken = await buildSentinelToken(deviceId, 'email_otp_validate', this.ua, this.secChUa, this.page);

    const headers = {
      'Accept': 'application/json',
      'Referer': state.currentUrl || state.continueUrl || `${OAUTH_ISSUER}/email-verification`,
      'Origin': OAUTH_ISSUER,
      'Content-Type': 'application/json',
      'Sec-Fetch-Site': 'same-origin',
      'oai-device-id': deviceId,
      ...generateDatadogTrace(),
    };
    if (sentinelToken) headers['openai-sentinel-token'] = sentinelToken;

    // 等待 OTP
    let initialOtpRequestedAt = Date.now() - 30000;
    if (proactivelySendOtp) {
      const requestedAt = Date.now();
      const sendOk = await this._sendEmailOtp(
        deviceId,
        state.currentUrl || state.continueUrl || `${OAUTH_ISSUER}/email-verification`,
      );
      if (sendOk) {
        initialOtpRequestedAt = requestedAt;
      } else {
        this._log('主动发送 OAuth OTP 失败，回退为等待已有邮件');
      }
    }
    const otpCode = await mailbox.waitForCode(
      email,
      this.config.otpWaitTimeout || 600,
      initialOtpRequestedAt,
    );
    if (!otpCode) {
      // 重发 OTP
      this._log('OAuth OTP 未收到，重发...');
      const resendOtpRequestedAt = Date.now();
      await this._sendEmailOtp(
        deviceId,
        state.currentUrl || state.continueUrl || `${OAUTH_ISSUER}/email-verification`,
      );
      const otpCode2 = await mailbox.waitForCode(
        email,
        this.config.otpResendWaitTimeout || 300,
        resendOtpRequestedAt,
      );
      if (!otpCode2) {
        this._log('OAuth OTP 仍然未收到');
        return null;
      }
      return this._validateOtp(otpCode2, headers);
    }

    return this._validateOtp(otpCode, headers);
  }

  async _validateOtp(code, headers) {
    this._log(`尝试 OTP: ${code}`);
    const result = await this._fetch(`${OAUTH_ISSUER}/api/accounts/email-otp/validate`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ code }),
    });

    if (!result.ok) {
      this._log(`OTP 无效: ${result.status} - ${(result.text || '').slice(0, 160)}`);
      return null;
    }

    const flowState = this._extractFlowState(result.data, result.url);
    this._log(`OTP 验证通过 page=${flowState.pageType}`);
    return flowState;
  }

  // ========================================================================
  // 主入口: login_and_get_tokens
  // ========================================================================

  /**
   * OAuth 登录获取 tokens
   * @returns {object|null} tokens { access_token, refresh_token, id_token, ... }
   */
  async loginAndGetTokens(email, password, options = {}) {
    const {
      deviceId: inputDeviceId,
      mailbox,
      forcePasswordLogin = true,
      forceNewBrowser = true,
      screenHint = 'login',
      completeAboutYouIfNeeded = true,
      proactivelySendOtpOnEmailPage = forceNewBrowser,
      firstName = '',
      lastName = '',
      birthdate = '',
    } = options;

    this.lastError = '';
    this.lastWorkspaceId = '';
    this.lastAuthIssue = '';

    let deviceId = inputDeviceId || generateDeviceId();
    this._log('开始 OAuth 登录流程...');

    // 生成 PKCE
    const [codeVerifier, codeChallenge] = generatePkce();
    const oauthState = crypto.randomBytes(32).toString('base64url');

    const authorizeParams = {
      response_type: 'code',
      client_id: this.oauthClientId,
      redirect_uri: this.oauthRedirectUri,
      scope: OAUTH_SCOPE,
      code_challenge: codeChallenge,
      code_challenge_method: 'S256',
      state: oauthState,
    };

    const authorizeUrl = `${OAUTH_ISSUER}/oauth/authorize`;

    // Bootstrap OAuth session
    this._log('步骤1: Bootstrap OAuth session...');
    const authorizeFinalUrl = await this._bootstrapOAuthSession(authorizeUrl, authorizeParams, deviceId);
    if (!authorizeFinalUrl) {
      this.lastError = 'Bootstrap 失败';
      return null;
    }

    const continueReferer = authorizeFinalUrl.startsWith(OAUTH_ISSUER) ? authorizeFinalUrl : `${OAUTH_ISSUER}/log-in`;

    let state = this._extractFlowState(null, authorizeFinalUrl);
    if (this._canContinueFromBootstrappedState(state)) {
      this._log(`Bootstrap reused existing auth session page=${state.pageType || 'unknown'}`);
    } else {

    // 提交邮箱
    state = await this._submitAuthorizeContinue(email, deviceId, continueReferer);
    if (!state) {
      this.lastError = '提交邮箱后未进入有效的 OAuth 状态';
      return null;
    }

    this._log(`OAuth 状态起点: page=${state.pageType}`);
    }

    this._log(`OAuth state start page=${state.pageType || 'unknown'}`);
    const seenStates = {};
    let referer = continueReferer;

    // 状态循环
    for (let step = 0; step < 20; step++) {
      const sig = `${state.pageType}|${state.method}|${state.continueUrl}|${state.currentUrl}`;
      seenStates[sig] = (seenStates[sig] || 0) + 1;
      this._log(`状态步进[${step + 1}/20]: page=${state.pageType || '-'} next=${(state.continueUrl || '').slice(0, 60)}`);

      if (seenStates[sig] > 2) {
        this.lastError = `OAuth 状态卡住: page=${state.pageType}`;
        return null;
      }

      // 检查是否有 authorization code
      const code = this._extractCodeFromState(state);
      if (code) {
        this._log(`获取到 authorization code: ${code.slice(0, 20)}...`);
        const tokens = await this._exchangeCodeForTokens(code, codeVerifier);
        if (tokens) {
          this._log('OAuth 登录成功');
        } else {
          this._log('换取 tokens 失败');
        }
        return tokens;
      }

      // login_password → 密码验证
      if (this._isLoginPassword(state) || (this._isCreateAccountPassword(state) && forcePasswordLogin)) {
        const nextState = await this._submitPasswordVerify(
          password, deviceId,
          state.currentUrl || state.continueUrl || referer,
        );
        if (!nextState) {
          this.lastError = '密码验证后未进入下一步 OAuth 状态';
          return null;
        }
        referer = state.currentUrl || referer;
        state = nextState;
        continue;
      }

      // email OTP
      if (this._isEmailOtp(state)) {
        if (!mailbox) {
          this.lastError = '需要邮箱 OTP 但缺少接码客户端';
          return null;
        }
        const nextState = await this._handleOtpVerification(email, deviceId, mailbox, state, {
          proactivelySendOtp: proactivelySendOtpOnEmailPage,
        });
        if (!nextState) {
          this.lastError = '邮箱 OTP 验证后未进入下一步 OAuth 状态';
          return null;
        }
        referer = state.currentUrl || referer;
        state = nextState;
        continue;
      }

      // about_you
      if (completeAboutYouIfNeeded && this._isAboutYou(state)) {
        this._log('命中 about_you，执行资料补全');
        const nextState = await this._submitAboutYou(
          firstName, lastName, birthdate, deviceId,
          state.currentUrl || state.continueUrl || referer,
        );
        if (!nextState) {
          this.lastError = 'about_you 提交后未进入下一步 OAuth 状态';
          return null;
        }
        referer = state.currentUrl || referer;
        state = nextState;
        continue;
      }

      // add_phone → 尝试 workspace 解析
      if (this._isAddPhone(state)) {
        this._log('命中 add_phone，尝试 workspace 选择');
        const consentUrl = `${OAUTH_ISSUER}/sign-in-with-chatgpt/codex/consent`;
        const { code, state: wsState, issue } = await this._submitWorkspaceAndOrg(consentUrl, deviceId);
        if (code) {
          this._log(`从 workspace 选择获取到 code: ${code.slice(0, 20)}...`);
          const tokens = await this._exchangeCodeForTokens(code, codeVerifier);
          if (!tokens) {
            this._log(`workspace 已获取且拿到 code，但未生成 token: ${this.lastAuthIssue || issue || '原因未明'}`);
          }
          return tokens;
        }
        if (wsState) {
          referer = state.currentUrl || referer;
          state = wsState;
          continue;
        }
        this.lastError = issue || this.lastAuthIssue || 'add_phone 阻断且无法解析 workspace';
        this._log(`workspace 已获取但未生成 token: ${this.lastError}`);
        return null;
      }

      // 需要导航
      if (this._requiresNavigation(state)) {
        const { code, state: navState } = await this._followFlowState(state, referer);
        if (code) {
          this._log(`获取到 authorization code: ${code.slice(0, 20)}...`);
          const tokens = await this._exchangeCodeForTokens(code, codeVerifier);
          return tokens;
        }
        referer = state.currentUrl || referer;
        state = navState;
        continue;
      }

      // 支持 workspace 解析的状态
      const target = `${state.continueUrl} ${state.currentUrl}`.toLowerCase();
      if (['consent', 'workspace_selection', 'organization_selection'].includes(state.pageType) ||
          target.includes('consent') || target.includes('workspace')) {
        const consentUrl = state.continueUrl || state.currentUrl || `${OAUTH_ISSUER}/sign-in-with-chatgpt/codex/consent`;
        const { code, state: wsState, issue } = await this._submitWorkspaceAndOrg(consentUrl, deviceId);
        if (code) {
          const tokens = await this._exchangeCodeForTokens(code, codeVerifier);
          if (!tokens) {
            this._log(`workspace 已获取且拿到 code，但未生成 token: ${this.lastAuthIssue || issue || '原因未明'}`);
          }
          return tokens;
        }
        if (wsState) {
          referer = state.currentUrl || referer;
          state = wsState;
          continue;
        }
        this.lastError = issue || this.lastAuthIssue || `workspace 已获取但未生成 token: page=${state.pageType}`;
        this._log(this.lastError);
        return null;
      }

      this.lastError = `未支持的 OAuth 状态: page=${state.pageType}`;
      return null;
    }

    this.lastError = 'OAuth 状态机超出最大步数';
    return null;
  }
}

module.exports = { OAuthClient, OAUTH_ISSUER };
