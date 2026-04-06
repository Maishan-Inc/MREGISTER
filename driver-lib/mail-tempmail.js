const { URL } = require('url');
const { chromium } = require('playwright-core');
const { BaseMailProvider } = require('./mail-base');
const { OTP_CODE_PATTERN } = require('./constants');

const DEFAULT_BASE_URL = 'https://web2.temp-mail.org';

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseTimestampInfo(value) {
  if (value === null || value === undefined || value === '') {
    return { timestamp: 0, precisionMs: 0 };
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      return { timestamp: 0, precisionMs: 0 };
    }
    if (value >= 1e12) {
      return { timestamp: value, precisionMs: 1 };
    }
    if (value >= 1e9) {
      return { timestamp: value * 1000, precisionMs: 1000 };
    }
    return { timestamp: value, precisionMs: 1 };
  }

  const text = String(value).trim();
  if (!text) {
    return { timestamp: 0, precisionMs: 0 };
  }
  if (/^\d{13}$/.test(text)) {
    return { timestamp: Number.parseInt(text, 10), precisionMs: 1 };
  }
  if (/^\d{10}$/.test(text)) {
    return { timestamp: Number.parseInt(text, 10) * 1000, precisionMs: 1000 };
  }

  const parsed = Date.parse(text);
  if (Number.isNaN(parsed)) {
    return { timestamp: 0, precisionMs: 0 };
  }
  return { timestamp: parsed, precisionMs: 1000 };
}

function isBlockedBody(body) {
  const text = String(body || '').toLowerCase();
  return (
    text.includes('please enable cookies') ||
    text.includes('sorry, you have been blocked') ||
    text.includes('cloudflare') ||
    text.includes('unable to access temp-mail.org')
  );
}

function previewText(value, maxLength = 240) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text) {
    return '';
  }
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}

class MailTempMail extends BaseMailProvider {
  constructor(config = {}) {
    super(config);
    this._baseUrl = config.tempmail?.baseUrl || DEFAULT_BASE_URL;
    this._proxy = String(config.tempmail?.proxy || '').trim();
    this._browserName = config.browser || 'edge';
    this._headless = Boolean(config.headless);
    this._accounts = new Map();
    this.browser = null;
    this.context = null;
    this.page = null;
    this._activeProxy = '';
    this._usedMessageSignatures = new Set();
  }

  async init() {
    const attempts = this._proxy
      ? [this._proxy, '']
      : [''];
    let lastError = null;

    for (const proxy of attempts) {
      try {
        await this._startBrowser(proxy);
        this._log(
          `Temp-mail browser initialized: ${this._baseUrl}${proxy ? ` via ${proxy}` : ' directly'}`,
        );
        return;
      } catch (error) {
        lastError = error;
        await this._teardown().catch(() => {});
        if (proxy) {
          this._log(`Temp-mail init failed via ${proxy}, retrying direct: ${error.message}`);
        }
      }
    }

    throw lastError || new Error('Failed to initialize temp-mail browser');
  }

  async _startBrowser(proxy) {
    const channel = this._browserName === 'chrome' ? 'chrome' : 'msedge';
    const launchOptions = {
      channel,
      headless: this._headless,
      args: [
        '--disable-blink-features=AutomationControlled',
        '--no-sandbox',
        '--disable-web-security',
      ],
    };

    if (proxy) {
      launchOptions.proxy = { server: proxy };
    }

    this.browser = await chromium.launch(launchOptions);
    this.context = await this.browser.newContext();
    this.page = await this.context.newPage();
    this._activeProxy = proxy;

    const response = await this.page.goto(this._baseUrl, {
      waitUntil: 'domcontentloaded',
      timeout: 30000,
    });
    await this.page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {});

    const status = response ? response.status() : 0;
    const bodyText = await this.page.locator('body').innerText().catch(() => '');
    if (status >= 400 || isBlockedBody(bodyText)) {
      throw new Error(`Temp-mail landing page blocked or unavailable (status=${status})`);
    }
  }

  async createAddress() {
    this._log('Creating temp mailbox...');
    const data = await this._requestJson('POST', '/mailbox');
    const address = String(data?.address || data?.mailbox || data?.email || '').trim();
    const token = String(data?.token || '').trim();

    if (!address || !token) {
      throw new Error(`Unexpected temp mailbox response: ${JSON.stringify(data)}`);
    }

    this._accounts.set(address, token);
    this._log(`Created temp mailbox: ${address}`);
    return { address, token };
  }

  async waitForCode(email, timeout = 600, otpSentAt = Date.now()) {
    const deadline = Date.now() + timeout * 1000;
    const pollIntervalMs = 5000;
    const baselineMessages = await this._fetchMessages(email);
    const baselineSignatures = new Set();

    for (const message of baselineMessages) {
      const signature = this._messageSignature(message);
      const code = this._extractCodeFromMessage(message);
      if (
        code &&
        this._isMessageFresh(message, otpSentAt) &&
        !this._usedMessageSignatures.has(signature)
      ) {
        this._usedCodes.add(code);
        this._usedMessageSignatures.add(signature);
        this._log(`Found OTP in initial snapshot: ${code}`);
        return code;
      }
      baselineSignatures.add(signature);
    }

    this._log(`Initial temp mailbox messages: ${baselineMessages.length}`);
    this._logMessageBatch('Initial temp mailbox content', baselineMessages);

    while (Date.now() < deadline) {
      await sleep(Math.min(pollIntervalMs, Math.max(0, deadline - Date.now())));
      const messages = await this._fetchMessages(email);
      this._log(`Polled temp mailbox messages: ${messages.length}`);
      this._logMessageBatch('Polled temp mailbox content', messages);

      for (const message of messages) {
        const signature = this._messageSignature(message);
        const code = this._extractCodeFromMessage(message);
        if (!code || this._usedMessageSignatures.has(signature)) {
          continue;
        }
        if (!this._isMessageFresh(message, otpSentAt)) {
          continue;
        }
        if (baselineSignatures.has(signature)) {
          continue;
        }

        this._usedCodes.add(code);
        this._usedMessageSignatures.add(signature);
        this._log(`Received new OTP from temp mailbox: ${code}`);
        return code;
      }
    }

    this._log(`OTP wait timed out after ${timeout}s`);
    return null;
  }

  _logMessageBatch(label, messages) {
    if (!Array.isArray(messages) || messages.length === 0) {
      return;
    }

    const limit = Math.min(messages.length, 3);
    for (let index = 0; index < limit; index += 1) {
      const message = messages[index];
      const extractedCode = this._extractCodeFromMessage(message);
      const createdAt =
        message?.createdAt ||
        message?.created_at ||
        message?.date ||
        message?.receivedAt ||
        message?.received_at ||
        message?.timestamp ||
        '';
      const subject = previewText(message?.subject || '(no subject)', 180);
      const bodyPreview = previewText(
        message?.body || message?.text || message?.content || '',
        280,
      );

      this._log(
        `${label} [${index + 1}/${messages.length}] subject="${subject}" time="${createdAt}" extractedCode=${extractedCode || '-'} body="${bodyPreview || '(empty)'}"`,
      );
    }
  }

  _messageSignature(message) {
    return [
      message?.id || message?._id || '',
      message?.subject || '',
      message?.createdAt || message?.created_at || message?.date || message?.timestamp || '',
      message?.body || message?.text || message?.content || '',
    ].join('|');
  }

  _isMessageFresh(message, otpSentAt) {
    if (!otpSentAt || otpSentAt <= 0) {
      return true;
    }

    const rawTime =
      message?.createdAt ||
      message?.created_at ||
      message?.date ||
      message?.receivedAt ||
      message?.received_at ||
      message?.timestamp;

    const { timestamp, precisionMs } = parseTimestampInfo(
      rawTime,
    );

    if (!timestamp) {
      return true;
    }

    const slackMs = Math.max(precisionMs, 2000);
    const fresh = timestamp + slackMs >= otpSentAt;

    if (!fresh) {
      this._log(
        `Message treated as old: messageTime=${timestamp} rawTime="${rawTime}" otpSentAt=${otpSentAt} slackMs=${slackMs}`,
      );
    }

    return fresh;
  }

  _extractCodeFromMessage(message) {
    const subject = String(message?.subject || '').trim();
    if (subject) {
      const lastToken = subject.split(/\s+/).pop() || '';
      if (/^\d{6}$/.test(lastToken)) {
        return lastToken;
      }
    }

    const text = `${subject} ${message?.body || message?.text || message?.content || ''}`;
    const match = text.match(OTP_CODE_PATTERN);
    return match ? match[1] : null;
  }

  async _fetchMessages(email) {
    const token = this._accounts.get(email);
    if (!token) {
      throw new Error(`No temp mailbox token found for ${email}`);
    }

    const data = await this._requestJson('GET', '/messages', `Bearer ${token}`);
    if (Array.isArray(data?.messages)) {
      return data.messages;
    }
    if (Array.isArray(data)) {
      return data;
    }
    return [];
  }

  async _requestJson(method, requestPath, authHeader) {
    if (!this.page) {
      throw new Error('Temp-mail browser is not initialized');
    }

    const targetUrl = new URL(requestPath, this._baseUrl).toString();
    const result = await this.page.evaluate(
      async ({ targetUrl, method, authHeader, baseUrl }) => {
        try {
          const response = await fetch(targetUrl, {
            method,
            credentials: 'include',
            referrer: baseUrl,
            headers: {
              Accept: 'application/json',
              ...(method === 'GET' ? { 'Cache-Control': 'no-cache' } : {}),
              ...(authHeader ? { Authorization: authHeader } : {}),
            },
          });

          return {
            status: response.status,
            contentType: response.headers.get('content-type') || '',
            body: await response.text(),
          };
        } catch (error) {
          return {
            error: error instanceof Error ? error.message : String(error),
          };
        }
      },
      {
        targetUrl,
        method,
        authHeader,
        baseUrl: this._baseUrl,
      },
    );

    if (result.error) {
      throw new Error(`Temp-mail browser fetch failed: ${result.error}`);
    }
    if (result.status !== 200) {
      throw new Error(
        `Temp mail API request failed: HTTP ${result.status} ${String(result.body || '').slice(0, 200)}`,
      );
    }
    try {
      return JSON.parse(String(result.body || 'null'));
    } catch (error) {
      throw new Error(
        `Temp mail JSON parse failed: ${error.message}, body: ${String(result.body || '').slice(0, 200)}`,
      );
    }
  }

  async _teardown() {
    if (this.page) {
      await this.page.close().catch(() => {});
      this.page = null;
    }
    if (this.context) {
      await this.context.close().catch(() => {});
      this.context = null;
    }
    if (this.browser) {
      await this.browser.close().catch(() => {});
      this.browser = null;
    }
    this._activeProxy = '';
  }

  async close() {
    this._accounts.clear();
    await this._teardown();
  }
}

module.exports = { MailTempMail };
