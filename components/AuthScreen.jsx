"use client";

import { useEffect, useRef, useState } from "react";
import { AGREEMENT_CONFIRM_TEXT, APP_NAME } from "@/src/lib/constants";
import { BusyButton } from "@/components/ui";

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(payload.detail || "请求失败");
  }
  return response.json();
}

function AgreementModal({ onComplete }) {
  const [step, setStep] = useState("read");
  const [hasReachedEnd, setHasReachedEnd] = useState(false);
  const [confirmationInput, setConfirmationInput] = useState("");
  const scrollRef = useRef(null);

  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  return (
    <div className="modal-shell is-open agreement-shell">
      <div className="agreement-backdrop" aria-hidden="true" />
      <section className="agreement-card" role="dialog" aria-modal="true">
        <div className="agreement-head">
          <p className="eyebrow">Maishan Inc.</p>
          <h2>开源项目非商业性协议</h2>
          <p className="subtle">更新日期：2026 年 4 月 6 日</p>
        </div>

        {step === "read" ? (
          <>
            <div
              className="agreement-scroll"
              ref={scrollRef}
              onScroll={(event) => {
                const element = event.currentTarget;
                const remaining = element.scrollHeight - element.scrollTop - element.clientHeight;
                if (remaining <= 8) {
                  setHasReachedEnd(true);
                }
              }}
            >
              <div className="agreement-intro">
                <p>本项目仅供学习、研究、非商业测试使用。</p>
                <p>禁止出售源码、部署服务、注册结果或任何变相商业包装。</p>
                <p>继续初始化即表示你理解并接受以上限制。</p>
              </div>
              <section className="agreement-section">
                <h3>一、适用范围</h3>
                <p>MREGISTER 的网页、后端、脚本、镜像配置和相关文档均受本协议约束。</p>
              </section>
              <section className="agreement-section">
                <h3>二、非商业限制</h3>
                <p>未经书面授权，不得将本项目用于销售、托管、代注册、收费分发、SaaS 接入等商业行为。</p>
              </section>
              <section className="agreement-section">
                <h3>三、风险说明</h3>
                <p>使用者需自行承担网络、第三方接口、账号风控、数据保管等风险，开发方不承担相关责任。</p>
              </section>
              <div className="agreement-closing">
                <strong>重点提醒</strong>
                <p>如果不同意，请立即停止初始化和使用。</p>
              </div>
            </div>
            <div className="agreement-actions">
              <span className={`agreement-status ${hasReachedEnd ? "ready" : ""}`.trim()}>
                {hasReachedEnd ? "已阅读至底部，可继续下一步。" : "请先滚动阅读到最底部。"}
              </span>
              <button type="button" disabled={!hasReachedEnd} onClick={() => setStep("confirm")}>
                下一步
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="agreement-confirm">
              <p>请输入以下内容确认你同意本协议：</p>
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
              <button type="button" className="ghost-btn" onClick={() => setStep("read")}>
                返回协议
              </button>
              <button type="button" disabled={confirmationInput.trim() !== AGREEMENT_CONFIRM_TEXT} onClick={onComplete}>
                确定
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

export function AuthScreen({ view }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [agreementAccepted, setAgreementAccepted] = useState(view !== "setup");

  async function handleSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(view === "setup" ? "/api/auth/setup" : "/api/auth/login", {
        method: "POST",
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
      <section className={`auth-card ${view === "setup" && !agreementAccepted ? "is-locked" : ""}`.trim()}>
        <p className="eyebrow">{APP_NAME}</p>
        <h1>{view === "setup" ? "首次打开请设置管理员密码" : "输入管理员密码进入控制台"}</h1>
        <p className="subtle">
          {view === "setup"
            ? "新版本已改为 Next.js + SQLite。本地初始化完成后才会开放任务和 API。"
            : "当前站点已启用密码保护。"}
        </p>
        <form className="stack auth-form" onSubmit={handleSubmit}>
          <label>
            <span>管理员密码</span>
            <input
              type="password"
              minLength="8"
              required
              disabled={view === "setup" && !agreementAccepted}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <BusyButton type="submit" busy={busy} disabled={view === "setup" && !agreementAccepted}>
            {view === "setup" ? "保存并进入后台" : "登录"}
          </BusyButton>
        </form>
        <p className="auth-error">{error}</p>
      </section>
      {view === "setup" && !agreementAccepted ? <AgreementModal onComplete={() => setAgreementAccepted(true)} /> : null}
    </main>
  );
}
