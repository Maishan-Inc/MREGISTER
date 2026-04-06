/**
 * Sentinel PoW 令牌求解器 (Node.js 版)
 * 翻译自 Python sentinel_token.py
 *
 * 支持两种请求方式:
 *   1. 通过浏览器 page.evaluate(fetch) 发送（推荐，真实 TLS 指纹）
 *   2. 回退到 Node.js https 模块（可能被 Cloudflare 拦截）
 */

const crypto = require('crypto');
const https = require('https');

const SENTINEL_REQ_URL = 'https://sentinel.openai.com/backend-api/sentinel/req';
const SENTINEL_REFERER = 'https://sentinel.openai.com/backend-api/sentinel/frame.html';

class SentinelTokenGenerator {
  constructor(deviceId, userAgent) {
    this.deviceId = deviceId || crypto.randomUUID();
    this.userAgent = userAgent || 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36';
    this.requirementsSeed = String(Math.random());
    this.sid = crypto.randomUUID();
  }

  static fnv1a32(text) {
    let h = 2166136261;
    for (let i = 0; i < text.length; i++) {
      h ^= text.charCodeAt(i);
      h = Math.imul(h, 16777619) >>> 0;
    }
    // murmurhash3 finalizer
    h ^= h >>> 16;
    h = Math.imul(h, 2246822507) >>> 0;
    h ^= h >>> 13;
    h = Math.imul(h, 3266489909) >>> 0;
    h ^= h >>> 16;
    return (h >>> 0).toString(16).padStart(8, '0');
  }

  static base64Encode(data) {
    const jsonStr = JSON.stringify(data);
    return Buffer.from(jsonStr, 'utf-8').toString('base64');
  }

  _getConfig() {
    const now = new Date();
    const dateStr = now.toUTCString().replace('GMT', 'GMT+0000 (Coordinated Universal Time)');

    const navProps = [
      'vendorSub', 'productSub', 'vendor', 'maxTouchPoints', 'scheduling',
      'userActivation', 'doNotTrack', 'geolocation', 'connection', 'plugins',
      'mimeTypes', 'pdfViewerEnabled', 'webkitTemporaryStorage', 'hardwareConcurrency',
    ];
    const navProp = navProps[crypto.randomInt(navProps.length)];

    const docKeys = ['location', 'implementation', 'URL', 'documentURI', 'compatMode'];
    const docKey = docKeys[crypto.randomInt(docKeys.length)];

    const winKeys = ['Object', 'Function', 'Array', 'Number', 'parseFloat', 'undefined'];
    const winKey = winKeys[crypto.randomInt(winKeys.length)];

    const perfNow = 1000 + Math.random() * 49000;
    const hardwareConcurrency = [4, 8, 12, 16][crypto.randomInt(4)];

    return [
      '1920x1080',                                  // [0] screen
      dateStr,                                       // [1] date
      4294705152,                                    // [2] jsHeapSizeLimit
      Math.random(),                                 // [3] → replaced by nonce
      this.userAgent,                                // [4] UA
      'https://sentinel.openai.com/sentinel/20260124ceb8/sdk.js', // [5] script src
      null,                                          // [6] script version
      null,                                          // [7] data-build
      'en-US',                                       // [8] language
      'en-US,en',                                    // [9] → replaced by elapsed
      Math.random(),                                 // [10]
      `${navProp}−undefined`,                        // [11] nav prop
      docKey,                                        // [12] doc key
      winKey,                                        // [13] win key
      perfNow,                                       // [14] performance.now
      this.sid,                                      // [15] sid
      '',                                            // [16] URLSearchParams
      hardwareConcurrency,                           // [17] hardwareConcurrency
      Date.now() - perfNow,                          // [18] timeOrigin
    ];
  }

  _runCheck(startTime, seed, difficulty, config, nonce) {
    config[3] = nonce;
    config[9] = Math.round((Date.now() - startTime));
    const encoded = SentinelTokenGenerator.base64Encode(config);
    const digest = SentinelTokenGenerator.fnv1a32(seed + encoded);
    if (digest.slice(0, difficulty.length) <= difficulty) {
      return encoded + '~S';
    }
    return null;
  }

  generateToken(seed, difficulty) {
    const MAX_ATTEMPTS = 500000;
    const ERROR_PREFIX = 'wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D';

    if (seed == null) {
      seed = this.requirementsSeed;
      difficulty = difficulty || '0';
    }
    if (difficulty == null || difficulty === '') {
      difficulty = '0';
    }
    difficulty = String(difficulty);

    const startTime = Date.now();
    const config = this._getConfig();

    for (let nonce = 0; nonce < MAX_ATTEMPTS; nonce++) {
      const value = this._runCheck(startTime, seed, difficulty, config, nonce);
      if (value) {
        return 'gAAAAAB' + value;
      }
    }
    return 'gAAAAAB' + ERROR_PREFIX + SentinelTokenGenerator.base64Encode(String(null));
  }

  generateRequirementsToken() {
    const config = this._getConfig();
    config[3] = 1;
    config[9] = Math.round(5 + Math.random() * 45);
    return 'gAAAAAC' + SentinelTokenGenerator.base64Encode(config);
  }
}

/**
 * 使用 Node.js https 模块发送 sentinel 请求（回退方案）
 */
function httpPost(url, body, headers) {
  return new Promise((resolve, reject) => {
    const urlObj = new (require('url').URL)(url);
    const options = {
      hostname: urlObj.hostname,
      port: urlObj.port || 443,
      path: urlObj.pathname + urlObj.search,
      method: 'POST',
      headers: {
        ...headers,
        'Content-Length': Buffer.byteLength(body),
      },
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        if (res.statusCode === 200) {
          try { resolve(JSON.parse(data)); } catch { resolve(null); }
        } else {
          resolve(null);
        }
      });
    });

    req.on('error', () => resolve(null));
    req.setTimeout(20000, () => { req.destroy(); resolve(null); });
    req.write(body);
    req.end();
  });
}

/**
 * 通过浏览器页面发送 sentinel 请求（真实 TLS 指纹）
 */
async function browserPost(page, url, body, headers) {
  try {
    return await page.evaluate(async ({ url, body, headers }) => {
      try {
        const resp = await fetch(url, {
          method: 'POST',
          headers,
          body,
        });
        if (resp.ok) {
          return await resp.json();
        }
        return null;
      } catch {
        return null;
      }
    }, { url, body, headers });
  } catch {
    return null;
  }
}

async function fetchSentinelChallenge(deviceId, flow = 'authorize_continue', userAgent, secChUa, page) {
  const generator = new SentinelTokenGenerator(deviceId, userAgent);
  const reqBody = JSON.stringify({
    p: generator.generateRequirementsToken(),
    id: deviceId,
    flow,
  });

  const headers = {
    'Content-Type': 'text/plain;charset=UTF-8',
    'Accept': '*/*',
    'Referer': SENTINEL_REFERER,
    'Origin': 'https://sentinel.openai.com',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
  };

  // 优先使用浏览器发送（真实 TLS 指纹，不会被 Cloudflare 拦截）
  if (page) {
    const result = await browserPost(page, SENTINEL_REQ_URL, reqBody, headers);
    if (result) return result;
  }

  // 回退到 Node.js https 模块
  return httpPost(SENTINEL_REQ_URL, reqBody, {
    ...headers,
    'User-Agent': userAgent || 'Mozilla/5.0',
    'sec-ch-ua': secChUa || '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
  });
}

/**
 * 构建 sentinel token
 * @param {string} deviceId
 * @param {string} flow
 * @param {string} userAgent
 * @param {string} secChUa
 * @param {import('playwright-core').Page} [page] - 可选，传入浏览器页面以通过真实 TLS 发送请求
 */
async function buildSentinelToken(deviceId, flow = 'authorize_continue', userAgent, secChUa, page) {
  const challenge = await fetchSentinelChallenge(deviceId, flow, userAgent, secChUa, page);
  if (!challenge) return null;

  const cValue = String(challenge.token || '').trim();
  if (!cValue) return null;

  const generator = new SentinelTokenGenerator(deviceId, userAgent);
  const powData = challenge.proofofwork || {};

  let pValue;
  if (powData.required && powData.seed) {
    pValue = generator.generateToken(powData.seed, powData.difficulty || '0');
  } else {
    pValue = generator.generateRequirementsToken();
  }

  return JSON.stringify({
    p: pValue,
    t: '',
    c: cValue,
    id: deviceId,
    flow,
  });
}

module.exports = {
  SentinelTokenGenerator,
  fetchSentinelChallenge,
  buildSentinelToken,
};
