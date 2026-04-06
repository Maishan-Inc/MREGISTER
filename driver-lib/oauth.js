/**
 * OAuth PKCE 辅助函数
 * 翻译自 Python oauth.py
 */

const crypto = require('crypto');
const https = require('https');
const { OAUTH_CLIENT_ID, OAUTH_AUTH_URL, OAUTH_TOKEN_URL, OAUTH_REDIRECT_URI, OAUTH_SCOPE } = require('./constants');

function b64urlNoPad(buffer) {
  return buffer.toString('base64url');
}

function sha256B64urlNoPad(text) {
  return b64urlNoPad(crypto.createHash('sha256').update(text, 'ascii').digest());
}

function randomState(nbytes = 16) {
  return crypto.randomBytes(nbytes).toString('base64url');
}

function pkceVerifier() {
  return crypto.randomBytes(64).toString('base64url');
}

function parseCallbackUrl(callbackUrl) {
  const candidate = (callbackUrl || '').trim();
  const result = { code: '', state: '', error: '', error_description: '' };
  if (!candidate) return result;

  let urlStr = candidate;
  if (!urlStr.includes('://')) {
    if (urlStr.startsWith('?')) {
      urlStr = `http://localhost${urlStr}`;
    } else if (/[/?#]/.test(urlStr) || urlStr.includes(':')) {
      urlStr = `http://${urlStr}`;
    } else if (urlStr.includes('=')) {
      urlStr = `http://localhost/?${urlStr}`;
    }
  }

  try {
    const { URL } = require('url');
    const u = new URL(urlStr);
    const query = u.searchParams;
    const fragment = new URLSearchParams(u.hash.slice(1));

    // Fragment params override query params when query is empty
    for (const [key] of fragment) {
      if (!query.get(key)) query.set(key, fragment.get(key));
    }

    result.code = (query.get('code') || '').trim();
    result.state = (query.get('state') || '').trim();
    result.error = (query.get('error') || '').trim();
    result.error_description = (query.get('error_description') || '').trim();

    if (result.code && !result.state && result.code.includes('#')) {
      const parts = result.code.split('#', 2);
      result.code = parts[0];
      result.state = parts[1];
    }

    if (!result.error && result.error_description) {
      [result.error, result.error_description] = [result.error_description, ''];
    }
  } catch {
    // Fallback regex
    const codeMatch = urlStr.match(/[?&]code=([^&#]+)/);
    const stateMatch = urlStr.match(/[?&]state=([^&#]+)/);
    if (codeMatch) result.code = codeMatch[1];
    if (stateMatch) result.state = stateMatch[1];
  }

  return result;
}

function jwtClaimsNoVerify(idToken) {
  if (!idToken || (idToken.match(/\./g) || []).length < 2) return {};
  try {
    const payloadB64 = idToken.split('.')[1];
    const pad = '='.repeat((4 - (payloadB64.length % 4)) % 4);
    const decoded = Buffer.from(payloadB64 + pad, 'base64url').toString('utf-8');
    return JSON.parse(decoded);
  } catch {
    return {};
  }
}

function generateOAuthUrl({ redirectUri = OAUTH_REDIRECT_URI, scope = OAUTH_SCOPE, clientId = OAUTH_CLIENT_ID } = {}) {
  const state = randomState();
  const codeVerifier = pkceVerifier();
  const codeChallenge = sha256B64urlNoPad(codeVerifier);

  const params = new URLSearchParams({
    client_id: clientId,
    response_type: 'code',
    redirect_uri: redirectUri,
    scope,
    state,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
    prompt: 'login',
    id_token_add_organizations: 'true',
    codex_cli_simplified_flow: 'true',
  });

  const authUrl = `${OAUTH_AUTH_URL}?${params.toString()}`;
  return { authUrl, state, codeVerifier, redirectUri };
}

function postForm(url, formBody, headers = {}) {
  return new Promise((resolve, reject) => {
    const target = new URL(url);
    const body = new URLSearchParams(formBody).toString();
    const req = https.request({
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port || 443,
      path: `${target.pathname}${target.search}`,
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Content-Length': Buffer.byteLength(body),
        ...headers,
      },
    }, (res) => {
      let text = '';
      res.on('data', (chunk) => {
        text += chunk;
      });
      res.on('end', () => {
        let data = null;
        try {
          data = JSON.parse(text);
        } catch {}
        resolve({
          status: res.statusCode || 0,
          headers: res.headers || {},
          text,
          data,
        });
      });
    });

    req.on('error', reject);
    req.setTimeout(30000, () => {
      req.destroy(new Error('OAuth token request timed out'));
    });
    req.write(body);
    req.end();
  });
}

async function exchangeAuthorizationCode({
  code,
  codeVerifier,
  redirectUri = OAUTH_REDIRECT_URI,
  clientId = OAUTH_CLIENT_ID,
} = {}) {
  if (!code) {
    throw new Error('Missing authorization code');
  }
  if (!codeVerifier) {
    throw new Error('Missing code verifier');
  }

  const result = await postForm(OAUTH_TOKEN_URL, {
    grant_type: 'authorization_code',
    code,
    redirect_uri: redirectUri,
    client_id: clientId,
    code_verifier: codeVerifier,
  });

  if (result.status >= 200 && result.status < 300 && result.data) {
    return result.data;
  }

  const errorMessage =
    result.data?.error_description ||
    result.data?.error ||
    result.text ||
    `HTTP ${result.status}`;
  throw new Error(`Token exchange failed: ${String(errorMessage).slice(0, 300)}`);
}

async function submitCallbackUrl({
  callbackUrl,
  expectedState = '',
  codeVerifier = '',
  redirectUri = OAUTH_REDIRECT_URI,
  clientId = OAUTH_CLIENT_ID,
} = {}) {
  const parsed = parseCallbackUrl(callbackUrl);

  if (parsed.error) {
    throw new Error(parsed.error_description || parsed.error);
  }
  if (!parsed.code) {
    throw new Error('Callback URL does not contain an authorization code');
  }
  if (expectedState && parsed.state !== expectedState) {
    throw new Error(`State mismatch: expected ${expectedState}, got ${parsed.state || '(empty)'}`);
  }

  const tokens = await exchangeAuthorizationCode({
    code: parsed.code,
    codeVerifier,
    redirectUri,
    clientId,
  });
  const claims = jwtClaimsNoVerify(tokens.id_token || '');
  const authClaims = claims['https://api.openai.com/auth'] || {};

  return {
    email: claims.email || '',
    access_token: tokens.access_token || '',
    refresh_token: tokens.refresh_token || '',
    id_token: tokens.id_token || '',
    account_id: authClaims.chatgpt_account_id || '',
    expires_in: tokens.expires_in || 0,
    scope: tokens.scope || '',
    token_type: tokens.token_type || '',
    type: 'codex',
  };
}

const decodeJwtPayload = jwtClaimsNoVerify;

module.exports = {
  b64urlNoPad,
  sha256B64urlNoPad,
  randomState,
  pkceVerifier,
  parseCallbackUrl,
  jwtClaimsNoVerify,
  decodeJwtPayload,
  generateOAuthUrl,
  exchangeAuthorizationCode,
  submitCallbackUrl,
};
