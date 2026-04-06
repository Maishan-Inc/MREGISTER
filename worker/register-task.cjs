const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');
const { ChatGPTClient } = require('../driver-lib/chatgpt-client');
const { OAuthClient } = require('../driver-lib/oauth-client');
const {
  generateRandomBirthday,
  generateRandomName,
  generateRandomPassword,
} = require('../driver-lib/utils');
const { OutlookManagerProvider } = require('./outlook-manager-provider.cjs');

function nowIso() {
  return new Date().toISOString();
}

function previewText(value, maxLength = 280) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text) {
    return '';
  }
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}

function classifyBlock(snapshot = {}, pageDiagnostics = {}) {
  const status = Number(snapshot?.status || 0);
  const parts = [
    snapshot?.url,
    snapshot?.text,
    snapshot?.errorMessage,
    snapshot?.headers?.server,
    snapshot?.headers?.location,
    pageDiagnostics?.url,
    pageDiagnostics?.title,
    pageDiagnostics?.bodyPreview,
  ].filter(Boolean).join('\n').toLowerCase();

  if (/cloudflare|cf-ray|attention required|just a moment|challenge-platform|cdn-cgi/.test(parts)) {
    return '疑似 Cloudflare / Challenge 页面';
  }
  if (/captcha|verify you are human|human verification|turnstile/.test(parts)) {
    return '疑似人机验证页面';
  }
  if (/access denied|forbidden|request blocked|unable to access|denied/.test(parts) || status === 403) {
    return '疑似被 OpenAI 边缘层直接拒绝';
  }
  if (/unsupported browser|enable javascript|enable cookies/.test(parts)) {
    return '疑似浏览器环境 / Cookie / JS 校验未通过';
  }
  if (/timed out|timeout|network|socket|tls|ssl|disconnected/.test(parts) || status === 0) {
    return '疑似网络 / TLS / 连接层异常';
  }
  return '原因未明，需结合页面内容继续判断';
}

function emit(event, payload = {}) {
  process.stdout.write(`__RESULT__ ${JSON.stringify({ event, ...payload })}\n`);
}

function log(message) {
  process.stdout.write(`[${nowIso()}] ${message}\n`);
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function safeSegment(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '') || 'item';
}

function writeJson(filePath, payload) {
  fs.writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

function parseArgs(argv) {
  const args = {};
  for (let index = 2; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith('--')) {
      continue;
    }
    args[token.slice(2)] = argv[index + 1];
    index += 1;
  }
  return args;
}

function resolveBrowserMode() {
  const raw = String(process.env.MREGISTER_BROWSER_MODE || 'headless').trim().toLowerCase();
  return raw === 'headed' ? 'headed' : 'headless';
}

function isHeadlessMode(browserMode) {
  return browserMode !== 'headed';
}

async function launchBrowser() {
  const browserMode = resolveBrowserMode();
  const attempts = [];
  const envPath = String(process.env.MREGISTER_BROWSER_PATH || '').trim();
  const envChannel = String(process.env.MREGISTER_BROWSER_CHANNEL || '').trim();
  const linuxChromium = '/usr/bin/chromium';

  if (envPath) {
    attempts.push({ executablePath: envPath });
  }
  if (envChannel) {
    attempts.push({ channel: envChannel });
  }
  if (process.platform === 'win32') {
    attempts.push({ channel: 'msedge' });
    attempts.push({ channel: 'chrome' });
  }
  if (process.platform !== 'win32' && fs.existsSync(linuxChromium)) {
    attempts.push({ executablePath: linuxChromium });
  }

  const seen = new Set();
  const baseArgs = [
    '--disable-blink-features=AutomationControlled',
    '--disable-dev-shm-usage',
    '--no-sandbox',
  ];

  for (const candidate of attempts) {
    const key = JSON.stringify(candidate);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    try {
      return await chromium.launch({
        headless: isHeadlessMode(browserMode),
        ...candidate,
        args: baseArgs,
      });
    } catch (error) {
      log(`Browser launch failed with ${key}: ${error.message}`);
    }
  }

  throw new Error('No available browser launch strategy');
}

async function createPage() {
  const browser = await launchBrowser();
  const context = await browser.newContext({
    locale: 'en-US',
    timezoneId: 'America/New_York',
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  return { browser, context, page };
}

async function collectPageDiagnostics(page) {
  try {
    const [title, url, content] = await Promise.all([
      page.title().catch(() => ''),
      Promise.resolve(page.url()).catch(() => ''),
      page.content().catch(() => ''),
    ]);
    const bodyPreview = previewText(
      String(content || '')
        .replace(/<script[\s\S]*?<\/script>/gi, ' ')
        .replace(/<style[\s\S]*?<\/style>/gi, ' ')
        .replace(/<[^>]+>/g, ' ')
        .replace(/&nbsp;/gi, ' '),
      360,
    );
    const cookies = await page.context().cookies().catch(() => []);
    return {
      url,
      title: previewText(title, 120),
      bodyPreview,
      cookieNames: cookies.map((item) => item.name).slice(0, 20),
    };
  } catch (error) {
    return {
      url: '',
      title: '',
      bodyPreview: '',
      cookieNames: [],
      errorMessage: error.message,
    };
  }
}

function attachRegistrationDiagnostics(chatgptClient) {
  const originalFetch = chatgptClient._fetch.bind(chatgptClient);
  chatgptClient._fetch = async (url, options = {}) => {
    const result = await originalFetch(url, options);
    if (String(url).includes('/api/auth/csrf')) {
      chatgptClient.__lastCsrfSnapshot = {
        status: result?.status || 0,
        url: result?.url || url,
        headers: result?.headers || {},
        text: previewText(result?.text || '', 320),
        errorMessage: result?.errorMessage || '',
      };
    }
    return result;
  };
}

async function logRegistrationDiagnostics(chatgptClient, runtime, failureMessage) {
  const pageDiagnostics = await collectPageDiagnostics(runtime.page);
  const csrfSnapshot = chatgptClient.__lastCsrfSnapshot || {};
  const classification = classifyBlock(csrfSnapshot, pageDiagnostics);

  log(`[Diag] Register entry failure: ${failureMessage}`);
  log(`[Diag] Classification: ${classification}`);
  if (csrfSnapshot.status || csrfSnapshot.errorMessage || csrfSnapshot.text) {
    log(
      `[Diag] CSRF snapshot: status=${csrfSnapshot.status || 0} url=${previewText(csrfSnapshot.url || '-', 180)} ` +
      `server=${previewText(csrfSnapshot.headers?.server || '-', 60)} content-type=${previewText(csrfSnapshot.headers?.['content-type'] || '-', 80)}`,
    );
    if (csrfSnapshot.text) {
      log(`[Diag] CSRF body: ${csrfSnapshot.text}`);
    }
    if (csrfSnapshot.errorMessage) {
      log(`[Diag] CSRF error: ${csrfSnapshot.errorMessage}`);
    }
  }
  log(
    `[Diag] Page snapshot: url=${previewText(pageDiagnostics.url || '-', 180)} title=${previewText(pageDiagnostics.title || '-', 120)} ` +
    `cookies=${pageDiagnostics.cookieNames.join(',') || '-'}`,
  );
  if (pageDiagnostics.bodyPreview) {
    log(`[Diag] Page body: ${pageDiagnostics.bodyPreview}`);
  }
}

function saveAccountArtifacts(outputDir, index, payload) {
  const folderName = `${String(index).padStart(3, '0')}-${safeSegment(payload.email)}`;
  const accountDir = path.join(outputDir, folderName);
  ensureDir(accountDir);
  writeJson(path.join(accountDir, 'account.json'), payload);
  if (payload.tokens) {
    writeJson(path.join(accountDir, 'tokens.json'), payload.tokens);
  }
}

async function registerOne(index, total, config, mailbox, results) {
  const { output_dir: outputDir } = config;
  const browserMode = resolveBrowserMode();
  const picked = await mailbox.acquireAccount();
  const email = picked.email;
  const account = picked.account || {};
  const password = generateRandomPassword();
  const [firstName, lastName] = generateRandomName();
  const birthdate = generateRandomBirthday();

  log(`[${index}/${total}] Selected mailbox ${email}`);

  const runtime = await createPage();
  try {
    const chatgptClient = new ChatGPTClient(runtime.page, {
      verbose: true,
      browserMode,
      fetchTimeoutMs: 30000,
    });
    attachRegistrationDiagnostics(chatgptClient);

    const [registerOk, registerMessage] = await chatgptClient.registerCompleteFlow(
      email,
      password,
      firstName,
      lastName,
      birthdate,
      mailbox,
      {
        stopBeforeAboutYouSubmission: true,
        otpWaitTimeout: 600,
        otpResendWaitTimeout: 300,
      },
    );

    if (!registerOk) {
      await logRegistrationDiagnostics(chatgptClient, runtime, String(registerMessage || 'register flow failed'));
      throw new Error(`register flow failed: ${registerMessage}`);
    }

    log(`[${index}/${total}] Register flow completed: ${registerMessage}`);

    const oauthClient = new OAuthClient(runtime.page, {
      verbose: true,
      browserMode,
      otpWaitTimeout: 600,
      otpResendWaitTimeout: 300,
    });

    const tokens = await oauthClient.loginAndGetTokens(email, password, {
      mailbox,
      forcePasswordLogin: true,
      forceNewBrowser: true,
      completeAboutYouIfNeeded: true,
      proactivelySendOtpOnEmailPage: true,
      firstName,
      lastName,
      birthdate,
    });

    if (!tokens?.access_token) {
      throw new Error(oauthClient.lastError || oauthClient.lastAuthIssue || 'oauth token exchange failed');
    }

    await mailbox.markRegistered(email, account.tag_keys || []);

    const accountPayload = {
      email,
      password,
      first_name: firstName,
      last_name: lastName,
      birthdate,
      created_at: nowIso(),
      platform: config.platform,
      task_id: config.task_id,
      tokens,
    };

    saveAccountArtifacts(outputDir, index, accountPayload);
    results.push({
      email,
      password,
      first_name: firstName,
      last_name: lastName,
      birthdate,
      created_at: accountPayload.created_at,
    });

    emit('account_success', { email });
    log(`[${index}/${total}] Completed successfully for ${email}`);
    return true;
  } catch (error) {
    emit('account_failed', { email, message: error.message });
    log(`[${index}/${total}] Failed for ${email}: ${error.message}`);
    return false;
  } finally {
    await runtime.page.close().catch(() => {});
    await runtime.context.close().catch(() => {});
    await runtime.browser.close().catch(() => {});
  }
}

async function main() {
  const args = parseArgs(process.argv);
  if (!args.config) {
    throw new Error('Missing --config');
  }

  const config = JSON.parse(fs.readFileSync(args.config, 'utf8'));
  const quantity = Math.max(1, Number(config.quantity || 1));
  ensureDir(config.output_dir);

  const mailbox = new OutlookManagerProvider({
    baseUrl: config.credential?.base_url,
    apiKey: config.credential?.api_key,
    categoryKey: config.credential?.category_key || 'mregister',
    tagKey: config.credential?.tag_key || 'chatgpt_registered',
  });

  const results = [];
  let successCount = 0;

  log('============================================================');
  log('MREGISTER Node worker started');
  log(`Task ID: ${config.task_id}`);
  log(`Target quantity: ${quantity}`);
  log(`Driver source: ${path.resolve(process.cwd(), 'driver-lib')}`);
  log(`Browser mode: ${resolveBrowserMode()}`);
  log(`Mail category: ${config.credential?.category_key || 'mregister'}`);
  log(`Success tag: ${config.credential?.tag_key || 'chatgpt_registered'}`);
  log('============================================================');

  try {
    await mailbox.init();

    for (let index = 1; index <= quantity; index += 1) {
      const ok = await registerOne(index, quantity, config, mailbox, results);
      if (ok) {
        successCount += 1;
      }
    }
  } finally {
    await mailbox.close().catch(() => {});
    writeJson(path.join(config.output_dir, 'accounts.json'), results);
  }

  log(`Worker finished, success=${successCount}, total=${quantity}`);
  process.exit(successCount >= quantity ? 0 : 1);
}

main().catch((error) => {
  log(`Fatal worker error: ${error.stack || error.message}`);
  process.exit(1);
});
