# MREGISTER Next

新版 `MREGISTER` 使用 `Next.js + React + SQLite` 重做控制台，任务执行层仍保留 Python `lib` 驱动，并把邮件系统切换到 OutlookManager API。

## 关键变化

- 后端持久化改为本地 `SQLite`
- 前端改为 `Next.js` 控制台
- 邮箱默认从 `mregister` 分类中挑选未打 `chatgpt_registered` 标签的账号
- 同一轮注册的发码、收码、完成注册都固定使用同一个邮箱
- 成功后自动为该邮箱打上 `chatgpt_registered` 标签

## 本地安装

```bash
npm install
python -m pip install -r worker/requirements.txt
npm run dev
```

打开：

```text
http://127.0.0.1:3000
```

首次进入会先显示协议确认和管理员密码初始化页面。

## OutlookManager 凭据

后台新增凭据时需要填写：

- `Base URL`
- `API Key`
- `category_key`
  默认 `mregister`
- `tag_key`
  默认 `chatgpt_registered`

如果分类或标签不存在，worker 会自动创建。

## 远程 Docker Compose

按你的要求，`docker-compose.yml` 默认直接拉取远程镜像：

```bash
docker compose pull
docker compose up -d
docker compose ps
```

默认映射端口：

```text
3345:3000
```

访问地址：

```text
http://服务器IP:3345
```

运行数据挂载到：

```text
./runtime
```

## 外部 API

创建 API Key 后，可调用：

- `POST /api/external/tasks`
- `GET /api/external/tasks/{task_id}`
- `GET /api/external/tasks/{task_id}/download`

创建任务示例：

```http
POST /api/external/tasks
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "platform": "chatgpt-register-lib",
  "quantity": 1,
  "name": "chatgpt-batch-01"
}
```
