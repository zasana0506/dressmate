// 视觉模型后端配置（可选）
//
// 两种配法，优先级如下：
//
// 1) 环境变量（推荐，Docker 部署用这个）
//    DRESSMATE_AI_BASE_URL=http://host.docker.internal:11434/v1
//    DRESSMATE_AI_API_KEY=sk-...
//    DRESSMATE_AI_MODEL=qwen2.5vl
//    任何 OpenAI 兼容的服务都行：Ollama、vLLM、OneAPI、各家云服务。
//
// 2) 这个文件（填 publishableKey）
//    仅在你有 WorkBuddy 云服务发布密钥时使用。
//    注意：这里的密钥会随前端页面下发给每个访问者，
//    所以绝对不要把它提交到公开仓库。
//
// 都不配也能用 —— 手工录入衣橱，或用中文文件名批量导入。
window.DM_CLOUD_CONFIG = {
  endpoint: "",
  publishableKey: "",
  resourceId: "",
};
