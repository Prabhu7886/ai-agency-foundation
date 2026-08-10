import type { Approval, Bootstrap, CodexStatus, Conversation, ConversationMessage, GitHubAction, GitHubStatus, ModelRouting, Project, PromptCompilation, SecurityScan, Task } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail ?? `Aegis request failed (${response.status})`);
  }
  return body as T;
}

export async function bootstrap(): Promise<Bootstrap> {
  await request<{ authenticated: boolean }>("/api/session", { method: "POST" });
  return request<Bootstrap>("/api/bootstrap");
}

export function createProject(payload: {
  name: string;
  description: string;
  root_path?: string;
  repository_url?: string;
}): Promise<Project> {
  return request<Project>("/api/projects", { method: "POST", body: JSON.stringify(payload) });
}

export function createAgent(payload: {
  name: string;
  role: string;
  description: string;
  model_policy: string;
  capabilities: string[];
}): Promise<Record<string, unknown>> {
  return request("/api/agents", { method: "POST", body: JSON.stringify(payload) });
}

export function createSkill(payload: {
  name: string;
  category: string;
  description: string;
  risk_level: string;
  capabilities: string[];
}): Promise<Record<string, unknown>> {
  return request("/api/skills", { method: "POST", body: JSON.stringify(payload) });
}

export function changePlugin(pluginId: string, enabled: boolean): Promise<Record<string, unknown>> {
  return request(`/api/plugins/${pluginId}`, { method: "POST", body: JSON.stringify({ enabled }) });
}

export function decideApproval(approvalId: string, decision: "approved" | "declined"): Promise<Record<string, unknown>> {
  return request(`/api/approvals/${approvalId}/decision`, { method: "POST", body: JSON.stringify({ decision }) });
}

export function chat(
  projectId: string,
  message: string,
  history: Array<{ role: "user" | "assistant"; content: string }> = [],
): Promise<{
  answer: string;
  provider: string;
  error?: string;
  task: { id: string; status: string };
  compilation?: {
    original_prompt: string;
    compiled_prompt: string;
    objective: string;
    risk_level: string;
    data_classification: string;
    compiler_mode: string;
  };
}> {
  return request("/api/chat", { method: "POST", body: JSON.stringify({ project_id: projectId, message, history }) });
}

export type ChatStreamEvent = {
  type: "start" | "status" | "routing" | "compilation" | "token" | "done" | "error";
  status?: string;
  content?: string;
  detail?: string;
  conversation?: Conversation;
  user_message?: ConversationMessage;
  assistant_message?: ConversationMessage;
  compilation?: PromptCompilation;
  routing?: ModelRouting;
  task?: Task;
  provider?: string;
  model?: string;
  tokens?: number;
  timings?: { prompt_rewrite_ms: number; first_token_ms: number | null; total_ms: number };
};

export async function streamChat(
  projectId: string,
  message: string,
  conversationId: string | null,
  onEvent: (event: ChatStreamEvent) => void,
): Promise<void> {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId, message, conversation_id: conversationId }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Aegis stream failed (${response.status})`);
  }
  if (!response.body) throw new Error("Aegis returned an empty stream");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const emitLine = (line: string) => {
    if (!line.trim()) return;
    onEvent(JSON.parse(line) as ChatStreamEvent);
  };
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    lines.forEach(emitLine);
    if (done) break;
  }
  emitLine(buffer);
}

export function getConversation(conversationId: string): Promise<Conversation> {
  return request(`/api/conversations/${conversationId}`);
}

export function archiveConversation(conversationId: string): Promise<Conversation> {
  return request(`/api/conversations/${conversationId}/archive`, { method: "POST" });
}

export function restoreConversation(conversationId: string): Promise<Conversation> {
  return request(`/api/conversations/${conversationId}/restore`, { method: "POST" });
}

export function deleteConversation(conversationId: string): Promise<{ deleted: boolean }> {
  return request(`/api/conversations/${conversationId}`, { method: "DELETE" });
}

export function requestResearch(
  projectId: string | null,
  query: string,
  purpose: "world_pulse" | "opportunity" = "world_pulse",
  category?: string,
): Promise<Record<string, unknown>> {
  return request("/api/research/requests", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, query, depth: "standard", purpose, category: category ?? (purpose === "opportunity" ? "business-opportunity" : "general") }),
  });
}

export function executeResearch(approvalId: string): Promise<Record<string, unknown>> {
  return request(`/api/research/requests/${approvalId}/execute`, { method: "POST" });
}

export function getGitHubStatus(projectId: string): Promise<GitHubStatus> {
  return request(`/api/github/status/${projectId}`);
}

export function requestGitHubOperation(payload: {
  project_id: string;
  action: GitHubAction;
  branch?: string;
  paths?: string[];
  message?: string;
  title?: string;
  body?: string;
  base?: string;
}): Promise<{ approval: import("./types").Approval }> {
  return request("/api/github/requests", { method: "POST", body: JSON.stringify(payload) });
}

export function executeGitHubOperation(approvalId: string): Promise<Record<string, unknown>> {
  return request(`/api/github/requests/${approvalId}/execute`, { method: "POST" });
}

export function runSecurityScan(projectId: string): Promise<SecurityScan> {
  return request("/api/security/scans", { method: "POST", body: JSON.stringify({ project_id: projectId }) });
}

export function getCodexStatus(): Promise<CodexStatus> {
  return request("/api/codex/status");
}

export function requestCodexDeviceLogin(): Promise<{ approval: Approval }> {
  return request("/api/codex/login/device", { method: "POST" });
}

export function executeCodexDeviceLogin(approvalId: string): Promise<{ loginId: string; verificationUrl: string; userCode: string }> {
  return request(`/api/codex/login/device/${approvalId}/execute`, { method: "POST" });
}

export function requestCodexTask(projectId: string, message: string): Promise<{ task: Task; approval: Approval }> {
  return request("/api/codex/requests", { method: "POST", body: JSON.stringify({ project_id: projectId, message }) });
}

export function executeCodexTask(approvalId: string): Promise<Record<string, unknown>> {
  return request(`/api/codex/requests/${approvalId}/execute`, { method: "POST" });
}

export function createOpportunity(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request("/api/opportunities", { method: "POST", body: JSON.stringify(payload) });
}

export function createSolution(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request("/api/solutions", { method: "POST", body: JSON.stringify(payload) });
}

export function requestDataJob(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request("/api/data-lab/jobs", { method: "POST", body: JSON.stringify(payload) });
}

export function executeDataJob(approvalId: string): Promise<Record<string, unknown>> {
  return request(`/api/data-lab/jobs/${approvalId}/execute`, { method: "POST" });
}

export function requestSolutionTransition(solutionId: string, targetStage: string, proof: string): Promise<Record<string, unknown>> {
  return request(`/api/solutions/${solutionId}/transitions`, { method: "POST", body: JSON.stringify({ target_stage: targetStage, proof }) });
}

export function executeSolutionTransition(approvalId: string): Promise<Record<string, unknown>> {
  return request(`/api/solutions/transitions/${approvalId}/execute`, { method: "POST" });
}

export function createAcademyCourse(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request("/api/academy/courses", { method: "POST", body: JSON.stringify(payload) });
}

export function updateAcademyCourse(courseId: string, status: string, progress: number): Promise<Record<string, unknown>> {
  return request(`/api/academy/courses/${courseId}`, { method: "PATCH", body: JSON.stringify({ status, progress }) });
}

export function createLearningMemory(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request("/api/learning/memory", { method: "POST", body: JSON.stringify(payload) });
}

export function decideLearningMemory(memoryId: string, status: "confirmed" | "disabled"): Promise<Record<string, unknown>> {
  return request(`/api/learning/memory/${memoryId}`, { method: "PATCH", body: JSON.stringify({ status }) });
}

export function transcribeVoice(blob: Blob): Promise<{ text: string; engine: string }> {
  return request("/api/voice/transcribe", { method: "POST", headers: { "Content-Type": blob.type || "audio/webm" }, body: blob });
}

export function speakVoice(text: string): Promise<Record<string, unknown>> {
  return request("/api/voice/speak", { method: "POST", body: JSON.stringify({ text }) });
}
