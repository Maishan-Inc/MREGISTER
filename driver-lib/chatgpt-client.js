/**
 * ChatGPT 注册客户端 (Phase A)
 * 使用 Playwright 浏览器上下文发起请求
 * 翻译自 Python chatgpt_client.py
 */

const { URL } = require('url');
const { randomChromeVersion, generateDeviceId, generateDatadogTrace, randomDelay } = require('./utils');
const { buildSentinelToken } = require('./sentinel');

const BASE = 'https://chatgpt.com';
const AUTH = 'https://auth.openai.com';

class ChatGPTClient {
  /**
   * @param {import('playwright-core').Page} page - Playwright 页面实例
   * @param {object} config - 配置
   */
  constructor(page, config = {}) {
    this.page = page;
    this.config = config;
    this.verbose = config.verbose !== false;
    this.browserMode = config.browserMode || 'headed';

    // Chrome 指纹
    const chrome = randomChromeVersion();
    this.chromeFull = chrome.fullVer;
    this.secChUa = chrome.secChUa;
    this.ua = chrome.ua;

    // 设备 ID
    this.deviceId = generateDeviceId();

    // 注册状态
    this.lastRegistrationState = null;
  }

  _log(msg) {
    if (this.verbose) {
      console.log(`  [Reg] ${msg}`);
    }
  }

  async _browserPause() {
    if (this.browserMode === 'headed') {
      await randomDelay(150, 450);
    }
  }

  /**
   * 在浏览器页面上下文中执行 fetch 请求
   * @returns {{ status: number, headers: object, data: any, url: string, text: string }}
   */
  async _fetch(url, options = {}) {
    const { method = 'GET', headers = {}, body = null, redirect = 'manual', timeoutMs } = options;
    const effectiveTimeoutMs = Math.max(1000, Number(timeoutMs || this.config.fetchTimeoutMs || 30000));

    const result = await this.page.evaluate(async ({ url, method, headers, body, redirect, timeoutMs }) => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(new Error(`fetch timeout after ${timeoutMs}ms`)), timeoutMs);
      try {
        const opts = { method, headers, redirect, signal: controller.signal };
        if (body !== null) {
          opts.body = body;
        }
        const resp = await fetch(url, opts);
        const respHeaders = {};
        resp.headers.forEach((v, k) => { respHeaders[k] = v; });
        let text;
        try { text = await resp.text(); } catch { text = ''; }
        let data;
        try { data = JSON.parse(text); } catch { data = null; }
        return {
          status: resp.status,
          headers: respHeaders,
          data,
          url: resp.url || url,
          text,
          type: resp.type,
          ok: resp.ok,
          redirected: resp.redirected,
        };
      } catch (e) {
        return { status: 0, headers: {}, data: null, url, text: e.message, type: 'error', ok: false, redirected: false, errorMessage: e.message };
      } finally {
        clearTimeout(timer);
      }
    }, { url, method, headers, body, redirect, timeoutMs: effectiveTimeoutMs });

    return result;
  }

  /**
   * 获取 Sentinel token (HTTP PoW 方式)
   */
  async _getSentinelToken(flow) {
    const token = await buildSentinelToken(
      this.deviceId,
      flow,
      this.ua,
      this.secChUa,
      this.page,
    );
    if (token) {
      this._log(`${flow}: 已通过 HTTP PoW 获取 sentinel token`);
    }
    return token;
  }

  // ========================================================================
  // 基础请求方法
  // ========================================================================

  /**
   * 访问 ChatGPT 首页，建立 session
   */
  async visitHomepage() {
    this._log('访问 ChatGPT 首页...');
    try {
      await this._browserPause();
      await this.page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded', timeout: 30000 });
      // 设置 oai-did cookie
      await this.page.context().addCookies([
        { name: 'oai-did', value: this.deviceId, domain: 'chatgpt.com', path: '/' },
        { name: 'oai-did', value: this.deviceId, domain: '.chatgpt.com', path: '/' },
        { name: 'oai-did', value: this.deviceId, domain: 'openai.com', path: '/' },
        { name: 'oai-did', value: this.deviceId, domain: 'auth.openai.com', path: '/' },
      ]);
      return true;
    } catch (e) {
      this._log(`访问首页失败: ${e.message}`);
      return false;
    }
  }

  /**
   * 获取 CSRF token
   */
  async getCsrfToken() {
    this._log('获取 CSRF token...');
    try {
      const result = await this._fetch(`${BASE}/api/auth/csrf`, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
          'Referer': `${BASE}/`,
          'Sec-Fetch-Site': 'same-origin',
        },
        timeoutMs: 20000,
      });
      if (result.ok && result.data?.csrfToken) {
        const token = result.data.csrfToken;
        this._log(`CSRF token: ${token.slice(0, 20)}...`);
        return token;
      }
      this._log(`鑾峰彇 CSRF token 澶辫触: ${result.status} - ${(result.text || '').slice(0, 180)}`);
    } catch (e) {
      this._log(`获取 CSRF token 失败: ${e.message}`);
    }
    return null;
  }

  /**
   * 提交邮箱，获取 authorize URL
   */
  async signin(email, csrfToken) {
    this._log(`提交邮箱: ${email}`);
    try {
      await this._browserPause();
      const params = new URLSearchParams({
        prompt: 'login',
        'ext-oai-did': this.deviceId,
        auth_session_logging_id: generateDeviceId(),
        screen_hint: 'login_or_signup',
        login_hint: email,
      });
      const formData = new URLSearchParams({
        callbackUrl: `${BASE}/`,
        csrfToken,
        json: 'true',
      });

      const result = await this._fetch(`${BASE}/api/auth/signin/openai?${params.toString()}`, {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Referer': `${BASE}/`,
          'Origin': BASE,
          'Content-Type': 'application/x-www-form-urlencoded',
          'Sec-Fetch-Site': 'same-origin',
        },
        body: formData.toString(),
        redirect: 'follow',
      });

      if (result.ok && result.data?.url) {
        this._log('获取到 authorize URL');
        return result.data.url;
      }
    } catch (e) {
      this._log(`提交邮箱失败: ${e.message}`);
    }
    return null;
  }

  /**
   * 访问 authorize URL，跟随重定向
   */
  async authorize(url, maxRetries = 3) {
    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        if (attempt > 0) {
          this._log(`访问 authorize URL... (尝试 ${attempt + 1}/${maxRetries})`);
          await randomDelay(1000, 2000);
        } else {
          this._log('访问 authorize URL...');
        }

        await this._browserPause();
        await this.page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
        const finalUrl = this.page.url();
        this._log(`重定向到: ${finalUrl}`);
        return finalUrl;
      } catch (e) {
        const errorMsg = e.message || '';
        const isTlsError = /TLS|SSL|curl.*35/i.test(errorMsg);
        if (isTlsError && attempt < maxRetries - 1) {
          this._log(`Authorize TLS 错误 (尝试 ${attempt + 1}/${maxRetries}): ${errorMsg.slice(0, 100)}`);
          continue;
        }
        this._log(`Authorize 失败: ${e.message}`);
        return '';
      }
    }
    return '';
  }

  /**
   * 注册用户（提交邮箱 + 密码）
   */
  async registerUser(email, password) {
    this._log(`注册用户: ${email}`);
    const ddTrace = generateDatadogTrace();

    const sentinelToken = await this._getSentinelToken('username_password_create');

    const headers = {
      'Accept': 'application/json',
      'Referer': `${AUTH}/create-account/password`,
      'Origin': AUTH,
      'Content-Type': 'application/json',
      'Sec-Fetch-Site': 'same-origin',
      'oai-device-id': this.deviceId,
      ...ddTrace,
    };
    if (sentinelToken) {
      headers['openai-sentinel-token'] = sentinelToken;
    }

    await this._browserPause();
    const result = await this._fetch(`${AUTH}/api/accounts/user/register`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ username: email, password }),
    });

    if (result.ok) {
      this._log('注册成功');
      return [true, '注册成功'];
    }
    const error = result.data?.error?.message || result.text?.slice(0, 200) || `HTTP ${result.status}`;
    this._log(`注册失败: ${result.status} - ${error}`);
    return [false, `HTTP ${result.status}: ${error}`];
  }

  /**
   * 触发发送邮箱验证码
   */
  async sendEmailOtp(referer = null) {
    this._log('触发发送验证码...');
    try {
      await this._browserPause();
      const result = await this._fetch(`${AUTH}/api/accounts/email-otp/send`, {
        method: 'GET',
        headers: {
          'Accept': 'application/json, text/plain, */*',
          'Referer': referer || `${AUTH}/create-account/password`,
          'Sec-Fetch-Site': 'same-origin',
        },
        redirect: 'follow',
      });

      this._log(`验证码发送状态: ${result.status}`);
      if (result.status !== 200) {
        this._log(`验证码发送失败: ${result.text?.slice(0, 180)}`);
        return false;
      }

      if (result.data && typeof result.data === 'object' && Object.keys(result.data).length > 0) {
        const pageType = this._inferPageType(result.data, result.url);
        this._log(`验证码发送响应: page=${pageType}`);
      } else {
        this._log('验证码发送响应: 非 JSON（按已触发处理）');
      }
      return true;
    } catch (e) {
      this._log(`发送验证码失败: ${e.message}`);
      return false;
    }
  }

  /**
   * 验证邮箱 OTP 码
   */
  async verifyEmailOtp(otpCode) {
    this._log(`验证 OTP 码: ${otpCode}`);
    const ddTrace = generateDatadogTrace();

    await this._browserPause();
    const result = await this._fetch(`${AUTH}/api/accounts/email-otp/validate`, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Referer': `${AUTH}/email-verification`,
        'Origin': AUTH,
        'Content-Type': 'application/json',
        'Sec-Fetch-Site': 'same-origin',
        ...ddTrace,
      },
      body: JSON.stringify({ code: otpCode }),
    });

    if (result.ok) {
      const data = result.data || {};
      const nextState = this._extractFlowState(data, result.url);
      this._log(`验证成功 page=${nextState.pageType} next=${(nextState.continueUrl || '').slice(0, 60)}`);
      return [true, nextState];
    }
    this._log(`验证失败: ${result.status} - ${(result.text || '').slice(0, 200)}`);
    return [false, `HTTP ${result.status}`];
  }

  // ========================================================================
  // 状态推断
  // ========================================================================

  async submitAboutYou(firstName, lastName, birthdate, referer = null) {
    const fullName = `${firstName} ${lastName}`.trim();
    if (!fullName || !birthdate) {
      this._log('about_you data is incomplete');
      return [false, 'missing profile details'];
    }

    const sentinelToken = await this._getSentinelToken('oauth_create_account');
    if (!sentinelToken) {
      this._log('about_you sentinel token unavailable');
      return [false, 'missing sentinel token'];
    }

    const headers = {
      'Accept': 'application/json',
      'Referer': referer || `${AUTH}/about-you`,
      'Origin': AUTH,
      'Content-Type': 'application/json',
      'Sec-Fetch-Site': 'same-origin',
      'oai-device-id': this.deviceId,
      'openai-sentinel-token': sentinelToken,
      ...generateDatadogTrace(),
    };

    await this._browserPause();
    const result = await this._fetch(`${AUTH}/api/accounts/create_account`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ name: fullName, birthdate }),
    });

    if (!result.ok) {
      this._log(`about_you submit failed: ${result.status} - ${(result.text || '').slice(0, 180)}`);
      return [false, `HTTP ${result.status}`];
    }

    const nextState = this._extractFlowState(result.data, result.url);
    this._log(`about_you submitted page=${nextState.pageType}`);
    return [true, nextState];
  }

  _inferPageType(data, currentUrl = '') {
    const raw = (data && typeof data === 'object') ? data : {};
    const page = raw.page || {};
    const pageType = page.type || '';
    if (pageType) return pageType.toLowerCase().replace(/[-/ ]/g, '_');

    // 从 URL 推断
    if (!currentUrl) return '';
    const urlStr = (currentUrl || '').toLowerCase();
    if (urlStr.includes('create-account/password')) return 'create_account_password';
    if (urlStr.includes('email-verification') || urlStr.includes('email-otp')) return 'email_otp_verification';
    if (urlStr.includes('about-you')) return 'about_you';
    if (urlStr.includes('log-in/password')) return 'login_password';
    if (urlStr.includes('add-phone')) return 'add_phone';
    if (urlStr.includes('callback')) return 'callback';
    if (urlStr.includes('chatgpt.com')) return 'chatgpt_home';
    return '';
  }

  _extractFlowState(data, currentUrl = '') {
    const raw = (data && typeof data === 'object') ? data : {};
    const page = raw.page || {};
    const payload = page.payload || {};
    const continueUrl = raw.continue_url || payload.url || '';
    const effectiveUrl = continueUrl || currentUrl;
    const pageType = this._inferPageType(data, effectiveUrl);
    const method = (raw.method || payload.method || 'GET').toUpperCase();

    return {
      pageType,
      continueUrl,
      method,
      currentUrl: effectiveUrl,
      payload: payload || {},
      raw,
    };
  }

  _isRegistrationComplete(state) {
    const pt = state.pageType || '';
    const url = (state.currentUrl || state.continueUrl || '').toLowerCase();
    return (
      ['callback', 'chatgpt_home', 'oauth_callback'].includes(pt) ||
      (url.includes('chatgpt.com') && !url.includes('redirect_uri'))
    );
  }

  _isPasswordRegistration(state) {
    return ['create_account_password', 'password'].includes(state.pageType);
  }

  _isEmailOtp(state) {
    const target = `${state.continueUrl || ''} ${state.currentUrl || ''}`.toLowerCase();
    return (
      state.pageType === 'email_otp_verification' ||
      target.includes('email-verification') ||
      target.includes('email-otp')
    );
  }

  _isAboutYou(state) {
    const target = `${state.continueUrl || ''} ${state.currentUrl || ''}`.toLowerCase();
    return state.pageType === 'about_you' || target.includes('about-you');
  }

  _isAddPhone(state) {
    const target = `${state.continueUrl || ''} ${state.currentUrl || ''}`.toLowerCase();
    return state.pageType === 'add_phone' || target.includes('add-phone');
  }

  _requiresNavigation(state) {
    if ((state.method || 'GET').toUpperCase() !== 'GET') return false;
    if (state.pageType === 'external_url' && state.continueUrl) return true;
    if (state.continueUrl && state.continueUrl !== state.currentUrl) return true;
    return false;
  }

  _isClearlyPastAboutYou(state) {
    const target = `${state.continueUrl || ''} ${state.currentUrl || ''}`.toLowerCase();
    return (
      this._isAddPhone(state) ||
      ['consent', 'workspace_selection', 'organization_selection', 'callback', 'oauth_callback', 'chatgpt_home'].includes(state.pageType) ||
      target.includes('consent') ||
      target.includes('workspace') ||
      target.includes('organization') ||
      (target.includes('chatgpt.com') && !target.includes('about-you'))
    );
  }

  async ensureAboutYouCompleted(firstName, lastName, birthdate, options = {}) {
    const {
      maxSteps = 6,
    } = options;

    let state = this.lastRegistrationState || this._extractFlowState(null, this.page.url());
    this._log(`about_you guard start: page=${state.pageType || '-'} url=${(state.currentUrl || '').slice(0, 80)}`);

    for (let step = 0; step < maxSteps; step += 1) {
      if (this._isAboutYou(state)) {
        const [ok, nextState] = await this.submitAboutYou(
          firstName,
          lastName,
          birthdate,
          state.currentUrl || state.continueUrl || `${AUTH}/about-you`,
        );
        if (!ok) return [false, `about_you submit failed: ${nextState}`];
        this.lastRegistrationState = nextState;
        return [true, nextState];
      }

      if (this._isClearlyPastAboutYou(state) || this._isRegistrationComplete(state)) {
        this.lastRegistrationState = state;
        return [true, state];
      }

      if (!this._requiresNavigation(state)) {
        this.lastRegistrationState = state;
        return [true, state];
      }

      const targetUrl = state.continueUrl || state.currentUrl;
      if (!targetUrl) {
        return [false, 'missing continue_url while checking about_you'];
      }

      try {
        await this.page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
        state = this._extractFlowState(null, this.page.url());
        this.lastRegistrationState = state;
        this._log(`about_you guard step=${step + 1} page=${state.pageType || '-'} next=${(state.continueUrl || '').slice(0, 60)}`);
      } catch (e) {
        return [false, `about_you guard navigation failed: ${e.message}`];
      }
    }

    return [false, 'about_you guard exceeded max steps'];
  }

  // ========================================================================
  // 注册主流程
  // ========================================================================

  /**
   * 完整注册流程
   * @param {string} email
   * @param {string} password
   * @param {string} firstName
   * @param {string} lastName
   * @param {string} birthdate
   * @param {object} mailbox - 邮箱 OTP 提供者 { waitForCode(email, timeout, otpSentAt) }
   * @param {object} options
   * @returns {[boolean, string|object]} [success, message/state]
   */
  async registerCompleteFlow(email, password, firstName, lastName, birthdate, mailbox, options = {}) {
    const {
      stopBeforeAboutYouSubmission = true,
      otpWaitTimeout = 600,
      otpResendWaitTimeout = 300,
    } = options;

    this._log(
      `注册状态机: stop_before_about_you=${stopBeforeAboutYouSubmission ? 'on' : 'off'}, ` +
      `otp_wait=${otpWaitTimeout}s, otp_resend_wait=${otpResendWaitTimeout}s`
    );

    const maxAuthAttempts = 3;
    let finalUrl = '';

    // Phase 1: 预授权
    for (let authAttempt = 0; authAttempt < maxAuthAttempts; authAttempt++) {
      if (authAttempt > 0) {
        this._log(`预授权阶段重试 ${authAttempt + 1}/${maxAuthAttempts}...`);
        this.deviceId = generateDeviceId();
      }

      // 1. 访问首页
      if (!(await this.visitHomepage())) {
        if (authAttempt < maxAuthAttempts - 1) continue;
        return [false, '访问首页失败'];
      }

      // 2. 获取 CSRF token
      const csrfToken = await this.getCsrfToken();
      if (!csrfToken) {
        if (authAttempt < maxAuthAttempts - 1) continue;
        return [false, '获取 CSRF token 失败'];
      }

      // 3. 提交邮箱
      const authUrl = await this.signin(email, csrfToken);
      if (!authUrl) {
        if (authAttempt < maxAuthAttempts - 1) continue;
        return [false, '提交邮箱失败'];
      }

      // 4. 访问 authorize URL
      finalUrl = await this.authorize(authUrl);
      if (!finalUrl) {
        if (authAttempt < maxAuthAttempts - 1) continue;
        return [false, 'Authorize 失败'];
      }

      this._log(`Authorize → ${new URL(finalUrl).pathname}`);

      // 检测 Cloudflare 中间页
      const finalPath = new URL(finalUrl).pathname;
      if (finalPath.includes('api/accounts/authorize') || finalPath === '/error') {
        this._log(`检测到 Cloudflare/SPA 中间页: ${finalUrl.slice(0, 160)}...`);
        if (authAttempt < maxAuthAttempts - 1) continue;
        return [false, `预授权被拦截: ${finalPath}`];
      }

      break;
    }

    // 初始状态
    let state = this._extractFlowState(null, finalUrl);
    this._log(`注册状态起点: page=${state.pageType} url=${(state.currentUrl || '').slice(0, 80)}`);

    let registerSubmitted = false;
    let otpVerified = false;
    let accountCreated = false;
    const seenStates = {};
    let otpSendAttempts = 0;
    let lastOtpRequestedAt = 0;

    // Phase 2: 状态循环
    for (let step = 0; step < 12; step++) {
      const sig = `${state.pageType}|${state.method}|${state.continueUrl}|${state.currentUrl}`;
      seenStates[sig] = (seenStates[sig] || 0) + 1;
      this._log(
        `注册状态推进: step=${step + 1} page=${state.pageType || '-'} ` +
        `next=${(state.continueUrl || '').slice(0, 60)} seen=${seenStates[sig]}`
      );

      if (seenStates[sig] > 2) {
        return [false, `注册状态卡住: page=${state.pageType}`];
      }

      // 检查是否完成
      if (this._isRegistrationComplete(state)) {
        this.lastRegistrationState = state;
        this._log('注册流程完成');
        return [true, '注册成功'];
      }

      // 密码注册
      if (this._isPasswordRegistration(state)) {
        this._log('全新注册流程');
        if (registerSubmitted) return [false, '注册密码阶段重复进入'];

        const [ok, msg] = await this.registerUser(email, password);
        if (!ok) return [false, `注册失败: ${msg}`];
        registerSubmitted = true;

        otpSendAttempts++;
        this._log(`发送注册验证码: attempt=${otpSendAttempts}`);
        lastOtpRequestedAt = Date.now();
        const sendOk = await this.sendEmailOtp(
          state.currentUrl || state.continueUrl || `${AUTH}/create-account/password`,
        );
        if (!sendOk) {
          this._log('发送验证码接口返回失败，继续等待邮箱中的验证码...');
        }

        state = this._extractFlowState(null, `${AUTH}/email-verification`);
        continue;
      }

      // 邮箱 OTP
      if (this._isEmailOtp(state)) {
        this._log('等待邮箱验证码...');

        const firstWaitSentAt = lastOtpRequestedAt || Date.now();
        let otpCode = await mailbox.waitForCode(email, otpWaitTimeout, firstWaitSentAt);

        if (!otpCode) {
          this._log(`首次等待未收到验证码，尝试重发后再等待 ${otpResendWaitTimeout}s`);
          otpSendAttempts++;
          lastOtpRequestedAt = Date.now();
          await this.sendEmailOtp(
            state.currentUrl || state.continueUrl || `${AUTH}/email-verification`,
          );
          otpCode = await mailbox.waitForCode(email, otpResendWaitTimeout, lastOtpRequestedAt);
        }

        if (!otpCode) return [false, '未收到验证码'];

        const [ok, nextState] = await this.verifyEmailOtp(otpCode);
        if (!ok) return [false, `验证码失败: ${nextState}`];
        otpVerified = true;
        state = nextState;
        this.lastRegistrationState = state;
        continue;
      }

      // about_you
      if (this._isAboutYou(state)) {
        if (!stopBeforeAboutYouSubmission && !accountCreated) {
          const [ok, nextState] = await this.submitAboutYou(
            firstName,
            lastName,
            birthdate,
            state.currentUrl || state.continueUrl || `${AUTH}/about-you`,
          );
          if (!ok) return [false, `about_you submit failed: ${nextState}`];
          accountCreated = true;
          state = nextState;
          this.lastRegistrationState = state;
          if (this._isAddPhone(state)) {
            this._log('account created and blocked on add_phone; treating signup as complete');
            return [true, 'account_created'];
          }
          continue;
        }
        if (stopBeforeAboutYouSubmission) {
          this.lastRegistrationState = state;
          this._log('注册链路已到 about_you，按 interrupt 流程停止');
          return [true, 'pending_about_you_submission'];
        }
        if (accountCreated) return [false, '填写信息阶段重复进入'];
        // 如果不停止，提交 about_you（AT 模式用）
        return [false, 'about_you 提交未实现（请使用 RT 模式）'];
      }

      // 需要导航
      if (this._requiresNavigation(state)) {
        const targetUrl = state.continueUrl || state.currentUrl;
        if (!targetUrl) return [false, '缺少可跟随的 continue_url'];
        try {
          await this.page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
          const navUrl = this.page.url();
          state = this._extractFlowState(null, navUrl);
          this.lastRegistrationState = state;
          continue;
        } catch (e) {
          return [false, `跳转失败: ${e.message}`];
        }
      }

      // 未知状态回退
      if (!registerSubmitted && !otpVerified && !accountCreated) {
        this._log(`未知起始状态，回退为全新注册流程: page=${state.pageType}`);
        state = this._extractFlowState(null, `${AUTH}/create-account/password`);
        continue;
      }

      return [false, `未支持的注册状态: page=${state.pageType}`];
    }

    return [false, '注册状态机超出最大步数'];
  }
}

module.exports = { ChatGPTClient, BASE, AUTH };
