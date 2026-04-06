/**
 * ChatGPT 注册常量定义
 */

// ============================================================================
// OAuth 相关常量
// ============================================================================

const OAUTH_CLIENT_ID = 'app_EMoamEEZ73f0CkXaXp7hrann';
const OAUTH_AUTH_URL = 'https://auth.openai.com/oauth/authorize';
const OAUTH_TOKEN_URL = 'https://auth.openai.com/oauth/token';
const OAUTH_REDIRECT_URI = 'http://localhost:1455/auth/callback';
const OAUTH_SCOPE = 'openid email profile offline_access';

// ============================================================================
// API 端点
// ============================================================================

const OPENAI_API_ENDPOINTS = {
  sentinel: 'https://sentinel.openai.com/backend-api/sentinel/req',
  signup: 'https://auth.openai.com/api/accounts/authorize/continue',
  register: 'https://auth.openai.com/api/accounts/user/register',
  passwordVerify: 'https://auth.openai.com/api/accounts/password/verify',
  passwordlessSendOtp: 'https://auth.openai.com/api/accounts/passwordless/send-otp',
  sendOtp: 'https://auth.openai.com/api/accounts/email-otp/send',
  validateOtp: 'https://auth.openai.com/api/accounts/email-otp/validate',
  createAccount: 'https://auth.openai.com/api/accounts/create_account',
  selectWorkspace: 'https://auth.openai.com/api/accounts/workspace/select',
  selectOrganization: 'https://auth.openai.com/api/accounts/organization/select',
};

// ============================================================================
// OTP 验证码相关
// ============================================================================

const OTP_CODE_PATTERN = /(?<!\d)(\d{6})(?!\d)/;
const OTP_MAX_ATTEMPTS = 40;
const OTP_CODE_SEMANTIC_PATTERN = /(?:code\s+is|验证码[是为]?\s*[:：]?\s*)(\d{6})/;

const OPENAI_EMAIL_SENDERS = [
  'noreply@openai.com',
  'no-reply@openai.com',
  '@openai.com',
  '.openai.com',
];

const OPENAI_VERIFICATION_KEYWORDS = [
  'verify your email',
  'verification code',
  '验证码',
  'your openai code',
  'code is',
  'one-time code',
];

// ============================================================================
// 密码 & 用户信息生成
// ============================================================================

const PASSWORD_CHARSET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%';
const DEFAULT_PASSWORD_LENGTH = 16;
const MIN_REGISTRATION_AGE = 20;
const MAX_REGISTRATION_AGE = 45;

const FIRST_NAMES = [
  'James', 'Robert', 'John', 'Michael', 'David', 'William', 'Richard',
  'Mary', 'Jennifer', 'Linda', 'Elizabeth', 'Susan', 'Jessica', 'Sarah',
  'Emily', 'Emma', 'Olivia', 'Sophia', 'Liam', 'Noah', 'Oliver', 'Ethan',
];

const LAST_NAMES = [
  'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller',
  'Davis', 'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Martin',
];

function generateRandomUserInfo() {
  const crypto = require('crypto');
  const name = FIRST_NAMES[crypto.randomInt(FIRST_NAMES.length)];
  const now = new Date();
  const currentYear = now.getFullYear();
  const birthYear = currentYear - MIN_REGISTRATION_AGE - crypto.randomInt(MAX_REGISTRATION_AGE - MIN_REGISTRATION_AGE + 1);
  const birthMonth = crypto.randomInt(1, 13); // 1-12
  const birthDay = crypto.randomInt(1, 29); // 1-28 (简化)
  const birthdate = `${birthYear}-${String(birthMonth).padStart(2, '0')}-${String(birthDay).padStart(2, '0')}`;
  return { name, birthdate };
}

// ============================================================================
// Chrome 指纹配置
// ============================================================================

const CHROME_PROFILES = [
  {
    major: 131,
    build: 6778,
    patchRange: [69, 205],
    secChUa: '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
  },
  {
    major: 133,
    build: 6943,
    patchRange: [33, 153],
    secChUa: '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
  },
  {
    major: 136,
    build: 7103,
    patchRange: [48, 175],
    secChUa: '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
  },
];

module.exports = {
  OAUTH_CLIENT_ID,
  OAUTH_AUTH_URL,
  OAUTH_TOKEN_URL,
  OAUTH_REDIRECT_URI,
  OAUTH_SCOPE,
  OPENAI_API_ENDPOINTS,
  OTP_CODE_PATTERN,
  OTP_MAX_ATTEMPTS,
  OTP_CODE_SEMANTIC_PATTERN,
  OPENAI_EMAIL_SENDERS,
  OPENAI_VERIFICATION_KEYWORDS,
  PASSWORD_CHARSET,
  DEFAULT_PASSWORD_LENGTH,
  MIN_REGISTRATION_AGE,
  MAX_REGISTRATION_AGE,
  FIRST_NAMES,
  LAST_NAMES,
  CHROME_PROFILES,
  generateRandomUserInfo,
};
