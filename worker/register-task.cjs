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

async function launchBrowser() {
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
        headless: true,
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
      browserMode: 'headless',
      fetchTimeoutMs: 30000,
    });

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
      throw new Error(`register flow failed: ${registerMessage}`);
    }

    log(`[${index}/${total}] Register flow completed: ${registerMessage}`);

    const oauthClient = new OAuthClient(runtime.page, {
      verbose: true,
      browserMode: 'headless',
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
