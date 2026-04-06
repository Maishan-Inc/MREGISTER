import React, { useEffect, useRef, useState } from 'react';
import { api, tr } from './config.js';

export function BusyButton({ busy, className = '', children, ...props }) {
  return (
    <button
      {...props}
      className={[className, busy ? 'is-busy' : ''].filter(Boolean).join(' ')}
      disabled={busy || props.disabled}
      aria-busy={busy ? 'true' : 'false'}
    >
      {children}
    </button>
  );
}

export function Modal({ open, title, message, confirmLabel, cancelLabel, onConfirm, onCancel }) {
  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        onCancel();
      }
    };
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = '';
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open, onCancel]);

  if (!open) {
    return null;
  }

  return (
    <div className="modal-shell is-open">
      <button type="button" className="modal-backdrop" aria-label={tr('close_sidebar')} onClick={onCancel} />
      <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <h3 id="modal-title">{title}</h3>
        <p className="subtle">{message}</p>
        <div className="modal-actions">
          {cancelLabel ? <button type="button" className="ghost-btn" onClick={onCancel}>{cancelLabel}</button> : null}
          <button type="button" onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

const AGREEMENT_CONFIRM_TEXT = '我同意此条款';

const AGREEMENT_SECTIONS = [
  {
    heading: '一、协议适用范围',
    body: '本协议适用于 Maishan Inc. 发布的 MREGISTER 开源项目及其相关前端、后端、脚本、构建产物与文档。任何个人、团队或组织在部署、使用、分发、修改本项目时，均视为已阅读并准备遵守本协议。',
  },
  {
    heading: '二、许可证说明',
    body: '本项目采用 CC BY-NC 4.0（署名-非商业性使用 4.0 国际）许可证。你可以在遵守署名和非商业性约束的前提下进行学习、研究、个人使用、技术验证和非商业二次开发，但不得将本项目或其衍生内容用于未经授权的商业活动。',
  },
  {
    heading: '三、非商业性限制',
    body: '未经 Maishan Inc. 书面授权，任何形式的商业化行为均被明确禁止。包括但不限于：出售本项目源码、出售本项目部署服务、出售通过本项目注册或批量生成的账户、将本项目打包后在任何渠道收费分发、将本项目接入付费 SaaS 或代注册服务、利用本项目为第三方提供有偿业务支持。',
  },
  {
    heading: '四、禁止规避与转售',
    body: '你不得删除、篡改、隐藏本项目中的版权、署名、协议提示或归属说明，不得以镜像包装、界面改名、二次封装、私有中转等方式规避本协议限制。任何试图通过技术或运营方式规避非商业限制的行为，均视为未经授权的侵权使用。',
  },
  {
    heading: '五、衍生作品与责任',
    body: '你可以为学习和非商业用途对本项目进行修改，但衍生版本仍应保留原始归属信息，并不得被用于未授权商业化。使用者应自行承担部署、运行、网络请求、第三方服务接入及由此产生的风险，开发商 Maishan Inc. 不对违规使用、封号、数据损失或第三方索赔承担责任。',
  },
  {
    heading: '六、侵权举报与处理',
    body: 'Maishan Inc. 欢迎任何用户、开发者或合作方举报未经授权的第三方侵权行为，尤其包括出售本项目源码、出售基于本项目注册的账户、提供未经授权的商业托管服务等行为。经核实的侵权线索，开发方保留公开说明、追究责任、要求下架及采取进一步维权措施的权利。',
  },
  {
    heading: '七、协议生效',
    body: '当你点击确认、继续初始化、部署、分发或实际使用本项目时，即表示你已完整阅读、理解并同意本协议全部内容。如不同意，请立即停止初始化与使用。',
  },
];

function SetupAgreementModal({ onComplete }) {
  const [step, setStep] = useState('read');
  const [hasReachedEnd, setHasReachedEnd] = useState(false);
  const [confirmationInput, setConfirmationInput] = useState('');
  const scrollRef = useRef(null);

  function handleScroll(event) {
    const element = event.currentTarget;
    const remaining = element.scrollHeight - element.scrollTop - element.clientHeight;
    if (remaining <= 8) {
      setHasReachedEnd(true);
    }
  }

  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = '';
    };
  }, []);

  return (
    <div className="modal-shell is-open agreement-shell">
      <div className="agreement-backdrop" aria-hidden="true" />
      <section className="agreement-card" role="dialog" aria-modal="true" aria-labelledby="agreement-title">
        <div className="agreement-head">
          <p className="eyebrow">Maishan Inc.</p>
          <h2 id="agreement-title">开源项目非商业性协议</h2>
          <p className="subtle">更新日期：2026年3月21日</p>
        </div>

        {step === 'read' ? (
          <>
            <div className="agreement-scroll" ref={scrollRef} onScroll={handleScroll}>
              <div className="agreement-intro">
                <p>开发商：Maishan Inc.</p>
                <p>许可证：CC BY-NC 4.0（署名-非商业性使用 4.0 国际）</p>
                <p>在继续初始化系统前，你必须完整阅读以下协议并明确同意相关限制。</p>
              </div>
              {AGREEMENT_SECTIONS.map((section) => (
                <section className="agreement-section" key={section.heading}>
                  <h3>{section.heading}</h3>
                  <p>{section.body}</p>
                </section>
              ))}
              <div className="agreement-closing">
                <strong>重点提醒</strong>
                <p>本项目严禁任何未经授权的商业化行为，尤其严禁在任何渠道出售本项目注册的账户、源码、部署服务或衍生商业工具。</p>
                <p>如你发现非授权第三方侵权行为，欢迎向 Maishan Inc. 举报。</p>
              </div>
            </div>
            <div className="agreement-actions">
              <span className={`agreement-status ${hasReachedEnd ? 'ready' : ''}`.trim()}>
                {hasReachedEnd ? '已阅读至底部，可继续下一步。' : '请先滚动阅读到最底部。'}
              </span>
              <button type="button" disabled={!hasReachedEnd} onClick={() => setStep('confirm')}>下一步</button>
            </div>
          </>
        ) : (
          <>
            <div className="agreement-confirm">
              <p>请输入以下内容以确认你已阅读并同意本协议：</p>
              <code>{AGREEMENT_CONFIRM_TEXT}</code>
              <label className="field-card agreement-confirm-input">
                <span>确认输入</span>
                <input
                  autoFocus
                  value={confirmationInput}
                  onChange={(event) => setConfirmationInput(event.target.value)}
                  placeholder="请手动输入完整内容"
                />
              </label>
            </div>
            <div className="agreement-actions">
              <button type="button" className="ghost-btn" onClick={() => setStep('read')}>返回协议</button>
              <button type="button" disabled={confirmationInput.trim() !== AGREEMENT_CONFIRM_TEXT} onClick={onComplete}>确定</button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

export function AuthScreen({ view }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [agreementAccepted, setAgreementAccepted] = useState(view !== 'setup');

  async function handleSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const path = view === 'setup' ? '/api/auth/setup' : '/api/auth/login';
      await api(path, {
        method: 'POST',
        body: JSON.stringify({ password }),
      });
      window.location.reload();
    } catch (submitError) {
      setError(submitError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <section className={`auth-card ${view === 'setup' && !agreementAccepted ? 'is-locked' : ''}`.trim()}>
        <p className="eyebrow">{tr('brand_name')}</p>
        <h1>{view === 'setup' ? tr('auth_setup_title') : tr('auth_login_title')}</h1>
        <p className="subtle">{view === 'setup' ? tr('auth_setup_desc') : tr('auth_login_desc')}</p>
        <form className="stack auth-form" onSubmit={handleSubmit}>
          <label>
            <span>{tr('auth_password')}</span>
            <input
              type="password"
              minLength="8"
              required
              disabled={view === 'setup' && !agreementAccepted}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <BusyButton type="submit" busy={busy} disabled={view === 'setup' && !agreementAccepted}>
            {view === 'setup' ? tr('auth_setup_submit') : tr('auth_login_submit')}
          </BusyButton>
        </form>
        <p className="auth-error">{error}</p>
      </section>
      {view === 'setup' && !agreementAccepted ? <SetupAgreementModal onComplete={() => setAgreementAccepted(true)} /> : null}
    </main>
  );
}
