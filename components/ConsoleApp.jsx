"use client";

import { useEffect, useMemo, useState } from "react";
import { APP_NAME, NAV_ITEMS } from "@/src/lib/constants";
import { BusyButton, Modal } from "@/components/ui";

const SECTION_TITLES = {
  dashboard: "总览",
  credentials: "凭据",
  "create-task": "新建任务",
  "task-detail": "任务详情",
  "api-keys": "API 接口",
  docs: "安装文档",
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (response.status === 401 || response.status === 403) {
    window.location.reload();
    throw new Error("鉴权失败");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(payload.detail || "请求失败");
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response;
}

function statusText(status) {
  return {
    queued: "排队中",
    running: "运行中",
    completed: "已完成",
    partial: "部分完成",
    failed: "失败",
    stopped: "已停止",
    interrupted: "已中断",
  }[status] || status;
}

export function ConsoleApp() {
  const [activeSection, setActiveSection] = useState("dashboard");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [busyKey, setBusyKey] = useState("");
  const [loadError, setLoadError] = useState("");
  const [flashMessage, setFlashMessage] = useState("");
  const [flashKey, setFlashKey] = useState("");
  const [confirmState, setConfirmState] = useState(null);
  const [statePayload, setStatePayload] = useState({
    platforms: {},
    defaults: {},
    credentials: [],
    tasks: [],
    api_keys: [],
    dashboard: {},
  });
  const [credentialDraft, setCredentialDraft] = useState({
    name: "",
    base_url: "",
    api_key: "",
    category_key: "mregister",
    tag_key: "chatgpt_registered",
    notes: "",
  });
  const [taskDraft, setTaskDraft] = useState({
    name: "",
    platform: "chatgpt-register-lib",
    quantity: "1",
    credential_id: "",
  });
  const [defaultCredentialId, setDefaultCredentialId] = useState("");
  const [apiKeyName, setApiKeyName] = useState("");
  const [selectedTaskId, setSelectedTaskId] = useState(null);

  const tasks = statePayload.tasks || [];
  const credentials = statePayload.credentials || [];
  const apiKeys = statePayload.api_keys || [];
  const selectedTask = useMemo(() => tasks.find((item) => item.id === selectedTaskId) || tasks[0] || null, [tasks, selectedTaskId]);

  useEffect(() => {
    refreshState();
    const timer = window.setInterval(() => {
      refreshState(true).catch(() => {});
    }, 4000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    setDefaultCredentialId(statePayload.defaults?.default_outlook_credential_id ? String(statePayload.defaults.default_outlook_credential_id) : "");
  }, [statePayload.defaults?.default_outlook_credential_id]);

  useEffect(() => {
    if (selectedTask) {
      setSelectedTaskId(selectedTask.id);
    }
  }, [selectedTask?.id]);

  async function refreshState(silent = false) {
    try {
      const payload = await api("/api/state");
      setStatePayload(payload);
      setLoadError("");
    } catch (error) {
      if (!silent) {
        setLoadError(error.message);
      }
    }
  }

  async function runAction(key, handler) {
    setBusyKey(key);
    try {
      await handler();
    } catch (error) {
      setLoadError(error.message);
    } finally {
      setBusyKey("");
    }
  }

  function isBusy(key) {
    return busyKey === key;
  }

  function showMessage(message) {
    setFlashMessage(message);
    window.clearTimeout(window.__mregisterToastTimer);
    window.__mregisterToastTimer = window.setTimeout(() => setFlashMessage(""), 3000);
  }

  async function handleLogout() {
    await runAction("logout", async () => {
      await api("/api/auth/logout", { method: "POST" });
      window.location.reload();
    });
  }

  async function handleCredentialSubmit(event) {
    event.preventDefault();
    await runAction("credential-save", async () => {
      await api("/api/credentials", {
        method: "POST",
        body: JSON.stringify(credentialDraft),
      });
      setCredentialDraft({
        name: "",
        base_url: "",
        api_key: "",
        category_key: "mregister",
        tag_key: "chatgpt_registered",
        notes: "",
      });
      showMessage("凭据已保存");
      await refreshState(true);
    });
  }

  async function handleSaveDefaults() {
    await runAction("defaults-save", async () => {
      await api("/api/settings/defaults", {
        method: "POST",
        body: JSON.stringify({ default_outlook_credential_id: defaultCredentialId || null }),
      });
      showMessage("默认凭据已更新");
      await refreshState(true);
    });
  }

  async function handleTaskSubmit(event) {
    event.preventDefault();
    await runAction("task-save", async () => {
      const response = await api("/api/tasks", {
        method: "POST",
        body: JSON.stringify({
          ...taskDraft,
          quantity: Number(taskDraft.quantity || 1),
          credential_id: taskDraft.credential_id || null,
        }),
      });
      setActiveSection("task-detail");
      setSelectedTaskId(response.id);
      setTaskDraft({
        name: "",
        platform: "chatgpt-register-lib",
        quantity: "1",
        credential_id: "",
      });
      showMessage(`任务 #${response.id} 已创建`);
      await refreshState(true);
    });
  }

  async function handleStopTask(taskId) {
    await runAction(`stop-${taskId}`, async () => {
      await api(`/api/tasks/${taskId}/stop`, { method: "POST" });
      showMessage(`任务 #${taskId} 已停止`);
      await refreshState(true);
    });
  }

  async function handleDeleteTask(taskId) {
    setConfirmState({
      title: "删除任务",
      message: `确认删除任务 #${taskId} 吗？`,
      confirmLabel: "删除",
      cancelLabel: "取消",
      onConfirm: async () => {
        setConfirmState(null);
        await runAction(`delete-task-${taskId}`, async () => {
          await api(`/api/tasks/${taskId}`, { method: "DELETE" });
          showMessage(`任务 #${taskId} 已删除`);
          await refreshState(true);
        });
      },
    });
  }

  async function handleDeleteCredential(credentialId, name) {
    setConfirmState({
      title: "删除凭据",
      message: `确认删除凭据 ${name} 吗？`,
      confirmLabel: "删除",
      cancelLabel: "取消",
      onConfirm: async () => {
        setConfirmState(null);
        await runAction(`delete-credential-${credentialId}`, async () => {
          await api(`/api/credentials/${credentialId}`, { method: "DELETE" });
          showMessage(`凭据 ${name} 已删除`);
          await refreshState(true);
        });
      },
    });
  }

  async function handleApiKeySubmit(event) {
    event.preventDefault();
    await runAction("api-key-save", async () => {
      const result = await api("/api/api-keys", {
        method: "POST",
        body: JSON.stringify({ name: apiKeyName }),
      });
      setApiKeyName("");
      setFlashKey(result.api_key);
      showMessage("API Key 已生成");
      await refreshState(true);
    });
  }

  async function handleDeleteApiKey(keyId) {
    await runAction(`delete-api-key-${keyId}`, async () => {
      await api(`/api/api-keys/${keyId}`, { method: "DELETE" });
      showMessage("API Key 已删除");
      await refreshState(true);
    });
  }

  function renderDashboard() {
    return (
      <section className="section-card active">
        <div className="metric-grid">
          <article className="metric-card"><span className="meta">任务总数</span><strong>{statePayload.dashboard.total_tasks || 0}</strong></article>
          <article className="metric-card"><span className="meta">运行中</span><strong>{statePayload.dashboard.running_tasks || 0}</strong></article>
          <article className="metric-card"><span className="meta">已完成</span><strong>{statePayload.dashboard.completed_tasks || 0}</strong></article>
          <article className="metric-card"><span className="meta">凭据数量</span><strong>{statePayload.dashboard.credential_count || 0}</strong></article>
        </div>

        <article className="panel">
          <div className="panel-head"><div><h3>默认设置</h3><span>API 创建任务时将优先使用这里的默认邮件凭据。</span></div></div>
          <div className="stack">
            <label className="field-card">
              <span>默认 OutlookManager 凭据</span>
              <select value={defaultCredentialId} onChange={(event) => setDefaultCredentialId(event.target.value)}>
                <option value="">不设置默认值</option>
                {credentials.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
              </select>
            </label>
            <BusyButton type="button" busy={isBusy("defaults-save")} onClick={handleSaveDefaults}>保存默认设置</BusyButton>
          </div>
        </article>

        <article className="panel">
          <div className="panel-head"><div><h3>最近任务</h3><span>点击任务可进入详情查看实时日志。</span></div></div>
          <div className="entity-list">
            {tasks.length ? tasks.slice(0, 6).map((task) => (
              <button type="button" className="simple-row" key={task.id} onClick={() => { setSelectedTaskId(task.id); setActiveSection("task-detail"); }}>
                <strong>{task.name}</strong>
                <span className="meta">#{task.id} | {statusText(task.status)} | {task.results_count}/{task.quantity}</span>
              </button>
            )) : <p className="empty">暂无任务</p>}
          </div>
        </article>
      </section>
    );
  }

  function renderCredentials() {
    return (
      <section className="section-card active">
        <div className="grid-two">
          <article className="panel">
            <div className="panel-head"><div><h3>新增 OutlookManager 凭据</h3><span>默认按 `mregister` 分类取号，成功后回写 `chatgpt_registered` 标签。</span></div></div>
            <form className="stack" onSubmit={handleCredentialSubmit}>
              <label className="field-card"><span>名称</span><input required value={credentialDraft.name} onChange={(event) => setCredentialDraft((value) => ({ ...value, name: event.target.value }))} /></label>
              <label className="field-card"><span>Base URL</span><input required value={credentialDraft.base_url} onChange={(event) => setCredentialDraft((value) => ({ ...value, base_url: event.target.value }))} /></label>
              <label className="field-card"><span>API Key</span><input required value={credentialDraft.api_key} onChange={(event) => setCredentialDraft((value) => ({ ...value, api_key: event.target.value }))} /></label>
              <div className="grid-two">
                <label className="field-card"><span>分类 key</span><input value={credentialDraft.category_key} onChange={(event) => setCredentialDraft((value) => ({ ...value, category_key: event.target.value.toLowerCase() }))} /></label>
                <label className="field-card"><span>成功标签 key</span><input value={credentialDraft.tag_key} onChange={(event) => setCredentialDraft((value) => ({ ...value, tag_key: event.target.value.toLowerCase() }))} /></label>
              </div>
              <label className="field-card"><span>备注</span><textarea value={credentialDraft.notes} onChange={(event) => setCredentialDraft((value) => ({ ...value, notes: event.target.value }))} /></label>
              <BusyButton type="submit" busy={isBusy("credential-save")}>保存凭据</BusyButton>
            </form>
          </article>

          <article className="panel">
            <div className="panel-head"><div><h3>已保存凭据</h3><span>删除前请确认没有运行中的任务正在使用该凭据。</span></div></div>
            <div className="entity-list">
              {credentials.length ? credentials.map((item) => (
                <article className="entity-card" key={item.id}>
                  <div>
                    <h3>{item.name}</h3>
                    <p className="meta">{item.base_url}</p>
                    <p className="notes">分类：{item.category_key} | 标签：{item.tag_key}</p>
                  </div>
                  <div className="entity-actions">
                    <BusyButton type="button" className="danger" busy={isBusy(`delete-credential-${item.id}`)} onClick={() => handleDeleteCredential(item.id, item.name)}>删除</BusyButton>
                  </div>
                </article>
              )) : <p className="empty">暂无凭据</p>}
            </div>
          </article>
        </div>
      </section>
    );
  }

  function renderCreateTask() {
    return (
      <section className="section-card active">
        <article className="panel">
          <div className="panel-head"><div><h3>创建注册任务</h3><span>任务会自动从 OutlookManager 的 `mregister` 分类里取一个未打成功标签的邮箱。</span></div></div>
          <form className="stack" onSubmit={handleTaskSubmit}>
            <label className="field-card"><span>任务名称</span><input value={taskDraft.name} onChange={(event) => setTaskDraft((value) => ({ ...value, name: event.target.value }))} placeholder="可留空自动命名" /></label>
            <div className="grid-two">
              <label className="field-card"><span>驱动</span><select value={taskDraft.platform} onChange={(event) => setTaskDraft((value) => ({ ...value, platform: event.target.value }))}><option value="chatgpt-register-lib">ChatGPT Register Lib</option></select></label>
              <label className="field-card"><span>目标数量</span><input type="number" min="1" value={taskDraft.quantity} onChange={(event) => setTaskDraft((value) => ({ ...value, quantity: event.target.value }))} /></label>
            </div>
            <label className="field-card">
              <span>指定凭据</span>
              <select value={taskDraft.credential_id} onChange={(event) => setTaskDraft((value) => ({ ...value, credential_id: event.target.value }))}>
                <option value="">使用默认凭据</option>
                {credentials.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
              </select>
            </label>
            <p className="field-tip field-tip--soft">邮件流规则：同一轮发送验证码与接收验证码始终使用同一个邮箱；成功后自动为该邮箱打上 `chatgpt_registered` 标签。</p>
            <BusyButton type="submit" busy={isBusy("task-save")}>创建并加入队列</BusyButton>
          </form>
        </article>
      </section>
    );
  }

  function renderTaskDetail() {
    return (
      <section className="section-card active">
        <div className="detail-layout">
          <article className="panel task-side-panel">
            <div className="panel-head"><div><h3>任务列表</h3><span>最新任务在最上面。</span></div></div>
            <div className="task-side-list">
              {tasks.length ? tasks.map((task) => (
                <button type="button" key={task.id} className={`task-side-item ${selectedTask?.id === task.id ? "selected" : ""}`.trim()} onClick={() => setSelectedTaskId(task.id)}>
                  <div className="task-side-item__top"><strong className="task-side-item__name">{task.name}</strong><span className="task-side-item__id">#{task.id}</span></div>
                  <div className="task-side-item__meta"><span className="task-side-item__count">{task.results_count}/{task.quantity}</span><span className="status-pill">{statusText(task.status)}</span></div>
                </button>
              )) : <p className="empty">暂无任务</p>}
            </div>
          </article>

          <article className="panel task-detail-panel">
            {selectedTask ? (
              <>
                <div className="task-detail-header">
                  <h3>{selectedTask.name}</h3>
                  <p className="subtle">#{selectedTask.id} | {selectedTask.platform_label} | 完成 {selectedTask.results_count}/{selectedTask.quantity} | 状态 {statusText(selectedTask.status)}</p>
                </div>
                <div className="task-actions">
                  <BusyButton type="button" busy={isBusy(`stop-${selectedTask.id}`)} disabled={!["queued", "running"].includes(selectedTask.status)} onClick={() => handleStopTask(selectedTask.id)}>停止任务</BusyButton>
                  <a className="ghost-btn button-link" href={`/api/tasks/${selectedTask.id}/download`}>下载压缩包</a>
                  <BusyButton type="button" className="danger" busy={isBusy(`delete-task-${selectedTask.id}`)} onClick={() => handleDeleteTask(selectedTask.id)}>删除任务</BusyButton>
                </div>
                <div className="console-box large-console">
                  <div className="console-title">实时控制台</div>
                  <pre id="task-console">{selectedTask.console_tail || "当前还没有控制台输出。"}</pre>
                </div>
              </>
            ) : <p className="empty">当前没有任务。</p>}
          </article>
        </div>
      </section>
    );
  }

  function renderApiKeys() {
    return (
      <section className="section-card active">
        <div className="grid-two">
          <article className="panel">
            <div className="panel-head"><div><h3>创建 API Key</h3><span>生成后只会显示一次，请立即保存。</span></div></div>
            <form className="stack" onSubmit={handleApiKeySubmit}>
              <label className="field-card"><span>名称</span><input required value={apiKeyName} onChange={(event) => setApiKeyName(event.target.value)} /></label>
              <BusyButton type="submit" busy={isBusy("api-key-save")}>生成 API Key</BusyButton>
            </form>
            {flashKey ? <div className="flash-key"><strong>新建成功，请立即保存</strong><code>{flashKey}</code></div> : null}
          </article>

          <article className="panel">
            <div className="panel-head"><div><h3>已有 API Key</h3><span>可用于外部程序调用创建任务、查询状态和下载结果。</span></div></div>
            <div className="entity-list">
              {apiKeys.length ? apiKeys.map((item) => (
                <article className="entity-card" key={item.id}>
                  <div>
                    <h3>{item.name}</h3>
                    <p className="meta">{item.key_prefix}... | 创建于 {item.created_at}</p>
                    <p className="notes">{item.last_used_at ? `最近使用：${item.last_used_at}` : "暂未使用"}</p>
                  </div>
                  <div className="entity-actions">
                    <BusyButton type="button" className="danger" busy={isBusy(`delete-api-key-${item.id}`)} onClick={() => handleDeleteApiKey(item.id)}>删除</BusyButton>
                  </div>
                </article>
              )) : <p className="empty">暂无 API Key</p>}
            </div>
          </article>
        </div>
      </section>
    );
  }

  function renderDocs() {
    const baseUrl = typeof window === "undefined" ? "http://127.0.0.1:3000" : window.location.origin;
    return (
      <section className="section-card active">
        <article className="panel docs-panel">
          <section className="docs-hero"><h3>部署、初始化与使用流程</h3><p>新版本采用 Next.js + React + SQLite，本地任务由 Python lib 驱动执行，Docker Compose 默认走远程镜像部署。</p></section>
          <section className="doc-card doc-feature">
            <div>
              <h3>新邮件系统</h3>
              <p>任务执行时会自动从 OutlookManager 中筛选 `mregister` 分类、且未打 `chatgpt_registered` 标签的邮箱，成功后立即回写标签。</p>
              <ul className="doc-note-list">
                <li>发送请求、接收验证码、完成注册始终绑定同一个邮箱。</li>
                <li>验证码默认取邮箱顶部最新邮件中的 6 位验证码。</li>
                <li>分类和标签不存在时，worker 会自动创建。</li>
              </ul>
            </div>
            <div className="doc-media-frame"><img className="doc-media" src="/docs-log-preview.jpg" alt="MREGISTER preview" /></div>
          </section>
          <div className="docs-grid">
            <section className="doc-card"><h3>本地安装</h3><ol className="doc-step-list"><li>`npm install`</li><li>`python -m pip install -r worker/requirements.txt`</li><li>`npm run dev`</li><li>浏览器打开 `http://127.0.0.1:3000`</li></ol></section>
            <section className="doc-card"><h3>远程 Docker Compose</h3><pre className="doc-pre">{`services:\n  mregister:\n    image: maishanhub/mregister:main\n    container_name: mregister\n    ports:\n      - "3000:3000"\n    volumes:\n      - ./runtime:/app/runtime\n    restart: unless-stopped`}</pre></section>
          </div>
          <section className="doc-card"><h3>首次初始化</h3><ol className="doc-step-list"><li>阅读协议并设置管理员密码。</li><li>在“凭据”页新增 OutlookManager API 凭据。</li><li>按需设为默认凭据。</li><li>进入“新建任务”创建注册任务。</li><li>在“任务详情”页查看控制台与下载结果。</li></ol></section>
          <div className="docs-grid">
            <section className="doc-card"><h3>外部 API</h3><div className="doc-code-block"><span className="doc-code-label">HTTP</span><pre className="doc-pre">{`POST ${baseUrl}/api/external/tasks\nAuthorization: Bearer YOUR_API_KEY\nContent-Type: application/json\n\n{\n  "platform": "chatgpt-register-lib",\n  "quantity": 1,\n  "name": "chatgpt-batch-01"\n}`}</pre></div></section>
            <section className="doc-card"><h3>状态查询</h3><div className="doc-code-block"><span className="doc-code-label">HTTP</span><pre className="doc-pre">{`GET ${baseUrl}/api/external/tasks/TASK_ID\nAuthorization: Bearer YOUR_API_KEY`}</pre></div></section>
          </div>
        </article>
      </section>
    );
  }

  function renderContent() {
    switch (activeSection) {
      case "dashboard": return renderDashboard();
      case "credentials": return renderCredentials();
      case "create-task": return renderCreateTask();
      case "task-detail": return renderTaskDetail();
      case "api-keys": return renderApiKeys();
      case "docs": return renderDocs();
      default: return renderDashboard();
    }
  }

  return (
    <>
      <div className={`admin-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`.trim()}>
        <aside className="sidebar">
          <div className="sidebar-top"><div className="sidebar-brand"><div className="brand-logo-wrap"><img className="brand-logo" src="/logo.png" alt={APP_NAME} /></div><div className="brand-copy"><h1>{APP_NAME}</h1></div></div></div>
          <nav className="sidebar-nav">
            {NAV_ITEMS.map(([id, label]) => (
              <button key={id} type="button" className={`nav-btn ${activeSection === id ? "active" : ""}`.trim()} onClick={() => setActiveSection(id)}>
                <span className="nav-btn__icon">{label.slice(0, 1)}</span>
                <span className="nav-btn__label">{label}</span>
              </button>
            ))}
          </nav>
          <BusyButton type="button" className="sidebar-logout" busy={isBusy("logout")} onClick={handleLogout}><span className="nav-btn__icon">退</span><span className="nav-btn__label">退出登录</span></BusyButton>
          <div className="sidebar-footer"><button type="button" className="sidebar-footer-toggle" onClick={() => setSidebarCollapsed((value) => !value)}><span className="nav-btn__icon sidebar-toggle-glyph">{sidebarCollapsed ? ">" : "<"}</span><span className="nav-btn__label">收起侧边栏</span></button></div>
        </aside>

        <main className="content-shell">
          <div className="content-topbar">
            <div className="content-topbar-copy"><span className="content-breadcrumb">工作区</span><span className="content-breadcrumb-sep">&gt;</span><span className="content-breadcrumb content-breadcrumb--current">{SECTION_TITLES[activeSection]}</span></div>
            <a className="topbar-link" href="https://github.com/Maishan-Inc/MREGISTER" target="_blank" rel="noreferrer">GH</a>
          </div>
          {flashMessage ? <div className="toast-banner toast-banner--success">{flashMessage}</div> : null}
          {loadError ? <div className="toast-error">{loadError}</div> : null}
          {renderContent()}
        </main>
      </div>

      <Modal
        open={Boolean(confirmState)}
        title={confirmState?.title}
        message={confirmState?.message}
        confirmLabel={confirmState?.confirmLabel}
        cancelLabel={confirmState?.cancelLabel}
        onConfirm={() => confirmState?.onConfirm?.()}
        onCancel={() => setConfirmState(null)}
      />
    </>
  );
}
