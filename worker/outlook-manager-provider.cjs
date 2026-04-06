const { BaseMailProvider } = require('../driver-lib/mail-base');
const {
  OTP_CODE_PATTERN,
  OPENAI_EMAIL_SENDERS,
  OPENAI_VERIFICATION_KEYWORDS,
} = require('../driver-lib/constants');

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function encodePathSegment(value) {
  return encodeURIComponent(String(value || '').trim());
}

function normalizeKey(value) {
  return String(value || '').trim().toLowerCase();
}

function stripHtml(value) {
  return String(value || '')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function parseTimestamp(value) {
  if (!value) {
    return 0;
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      return 0;
    }
    return value >= 1e12 ? value : value * 1000;
  }
  const text = String(value).trim();
  if (!text) {
    return 0;
  }
  if (/^\d{13}$/.test(text)) {
    return Number.parseInt(text, 10);
  }
  if (/^\d{10}$/.test(text)) {
    return Number.parseInt(text, 10) * 1000;
  }
  const parsed = Date.parse(text);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function uniqueKeys(values) {
  return [...new Set((values || []).map((item) => normalizeKey(item)).filter(Boolean))];
}

class OutlookManagerProvider extends BaseMailProvider {
  constructor(config = {}) {
    super(config);
    this.baseUrl = String(config.baseUrl || '').trim().replace(/\/+$/, '');
    this.apiKey = String(config.apiKey || '').trim();
    this.categoryKey = normalizeKey(config.categoryKey || 'mregister');
    this.tagKey = normalizeKey(config.tagKey || 'chatgpt_registered');
    this.pollIntervalMs = Math.max(2000, Number(config.pollIntervalMs || 5000));
    this._initialized = false;
    this._reservedEmails = new Set();
    this._consumedMessages = new Map();
  }

  async init() {
    if (this._initialized) {
      return;
    }
    if (!this.baseUrl || !this.apiKey) {
      throw new Error('OutlookManager 凭据不完整');
    }
    await this._ensureClassificationKeys();
    this._initialized = true;
    this._log(`OutlookManager ready: ${this.baseUrl}`);
  }

  async createAddress() {
    const payload = await this.acquireAccount();
    return { address: payload.email, account: payload.account };
  }

  async acquireAccount() {
    await this.init();

    for (let page = 1; page <= 20; page += 1) {
      const data = await this._requestJson('GET', '/accounts', {
        searchParams: {
          page: String(page),
          page_size: '100',
          category_key: this.categoryKey,
        },
      });
      const accounts = Array.isArray(data?.accounts) ? data.accounts : [];
      for (const account of accounts) {
        const email = normalizeKey(account?.email_id);
        const tagKeys = uniqueKeys(account?.tag_keys);
        if (!email) {
          continue;
        }
        if (this._reservedEmails.has(email)) {
          continue;
        }
        if (tagKeys.includes(this.tagKey)) {
          continue;
        }
        this._reservedEmails.add(email);
        this._log(`Picked mailbox: ${email}`);
        return { email, account: { ...account, tag_keys: tagKeys } };
      }

      const totalPages = Number(data?.total_pages || page);
      if (!accounts.length || page >= totalPages) {
        break;
      }
    }

    throw new Error(`分类 ${this.categoryKey} 下没有可用邮箱`);
  }

  async markRegistered(email, existingTags = []) {
    await this.init();
    const normalizedEmail = normalizeKey(email);
    const tagKeys = uniqueKeys([...(existingTags || []), this.tagKey]);
    await this._requestJson('PUT', `/accounts/${encodePathSegment(normalizedEmail)}/classification`, {
      json: {
        category_key: this.categoryKey,
        tag_keys: tagKeys,
      },
    });
    this._log(`Tagged mailbox as registered: ${normalizedEmail}`);
  }

  async waitForCode(email, timeout = 600, otpSentAt = Date.now()) {
    await this.init();
    const normalizedEmail = normalizeKey(email);
    const consumed = this._consumedMessages.get(normalizedEmail) || new Set();
    const baseline = new Set();
    const deadline = Date.now() + Number(timeout || 600) * 1000;

    const firstBatch = await this._listEmails(normalizedEmail, true);
    const firstCode = await this._findFreshOtp(normalizedEmail, firstBatch, otpSentAt, consumed, baseline);
    if (firstCode) {
      this._consumedMessages.set(normalizedEmail, consumed);
      return firstCode;
    }

    while (Date.now() < deadline) {
      await sleep(Math.min(this.pollIntervalMs, Math.max(0, deadline - Date.now())));
      const emails = await this._listEmails(normalizedEmail, true);
      const code = await this._findFreshOtp(normalizedEmail, emails, otpSentAt, consumed, baseline);
      if (code) {
        this._consumedMessages.set(normalizedEmail, consumed);
        return code;
      }
    }

    this._consumedMessages.set(normalizedEmail, consumed);
    this._log(`OTP timeout: ${normalizedEmail}`);
    return null;
  }

  async close() {}

  async _ensureClassificationKeys() {
    const data = await this._requestJson('GET', '/classifications');
    const categories = Array.isArray(data?.categories) ? data.categories : [];
    const tags = Array.isArray(data?.tags) ? data.tags : [];
    const categoryExists = categories.some((item) => normalizeKey(item?.key) === this.categoryKey);
    const tagExists = tags.some((item) => normalizeKey(item?.key) === this.tagKey);

    if (!categoryExists) {
      await this._requestJson('POST', '/classifications/categories', {
        json: {
          name_zh: 'MREGISTER分类',
          name_en: this.categoryKey,
        },
      });
      this._log(`Created category: ${this.categoryKey}`);
    }

    if (!tagExists) {
      await this._requestJson('POST', '/classifications/tags', {
        json: {
          name_zh: 'CHATGPT Registered',
          name_en: this.tagKey,
        },
      });
      this._log(`Created tag: ${this.tagKey}`);
    }
  }

  async _listEmails(email, refresh = false) {
    const data = await this._requestJson('GET', `/emails/${encodePathSegment(email)}`, {
      searchParams: {
        folder: 'inbox',
        page: '1',
        page_size: '20',
        refresh: refresh ? 'true' : 'false',
      },
    });
    return Array.isArray(data?.emails) ? data.emails : [];
  }

  async _getEmailDetail(email, messageId) {
    return this._requestJson('GET', `/emails/${encodePathSegment(email)}/${encodePathSegment(messageId)}`);
  }

  async _findFreshOtp(email, emails, otpSentAt, consumed, baseline) {
    for (const message of emails || []) {
      const messageId = String(message?.message_id || '').trim();
      if (!messageId) {
        continue;
      }

      const detail = await this._getEmailDetail(email, messageId).catch(() => null);
      const signature = this._messageSignature(message, detail);
      const createdAt = parseTimestamp(
        detail?.date ||
        message?.date ||
        detail?.created_at ||
        message?.created_at ||
        detail?.received_at ||
        message?.received_at ||
        detail?.timestamp ||
        message?.timestamp,
      );

      if (consumed.has(signature)) {
        continue;
      }
      if (createdAt && otpSentAt && createdAt + 2000 < otpSentAt) {
        baseline.add(signature);
        continue;
      }

      const code = this._extractCode(detail || message);
      if (!code) {
        baseline.add(signature);
        continue;
      }

      const looksLikeOpenAi = this._looksLikeOpenAiMail(detail || message);
      if (!looksLikeOpenAi && baseline.has(signature)) {
        continue;
      }

      consumed.add(signature);
      this._log(`OTP received for ${email}: ${code}`);
      return code;
    }

    return null;
  }

  _messageSignature(message, detail) {
    return [
      detail?.message_id || message?.message_id || '',
      detail?.subject || message?.subject || '',
      detail?.date || message?.date || '',
    ].join('|');
  }

  _extractCode(message) {
    const subject = String(message?.subject || '').trim();
    const content = [
      subject,
      message?.body_plain,
      stripHtml(message?.body_html),
      message?.body,
      message?.snippet,
    ].filter(Boolean).join(' ');

    const subjectLastToken = subject.split(/\s+/).pop() || '';
    if (/^\d{6}$/.test(subjectLastToken)) {
      return subjectLastToken;
    }

    const match = String(content).match(OTP_CODE_PATTERN);
    return match ? match[1] : null;
  }

  _looksLikeOpenAiMail(message) {
    const fromValue = normalizeKey(message?.from_email || message?.from || '');
    const subject = normalizeKey(message?.subject || '');
    const body = normalizeKey(
      [message?.body_plain, stripHtml(message?.body_html), message?.body, message?.snippet]
        .filter(Boolean)
        .join(' '),
    );

    const senderMatched = OPENAI_EMAIL_SENDERS.some((item) => fromValue.includes(normalizeKey(item)));
    const keywordMatched = OPENAI_VERIFICATION_KEYWORDS.some((item) => subject.includes(normalizeKey(item)) || body.includes(normalizeKey(item)));
    return senderMatched || keywordMatched;
  }

  async _requestJson(method, requestPath, options = {}) {
    const url = new URL(requestPath, `${this.baseUrl}/`);
    for (const [key, value] of Object.entries(options.searchParams || {})) {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value));
      }
    }

    const response = await fetch(url, {
      method,
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        'X-API-Key': this.apiKey,
        Accept: 'application/json',
        ...(options.json ? { 'Content-Type': 'application/json' } : {}),
      },
      body: options.json ? JSON.stringify(options.json) : undefined,
    });

    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = null;
    }

    if (!response.ok) {
      const detail = data?.detail || data?.message || text || `HTTP ${response.status}`;
      throw new Error(`OutlookManager API error ${response.status}: ${detail}`);
    }

    return data;
  }
}

module.exports = { OutlookManagerProvider };
