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
  scheduleId?: string,
): Promise<Record<string, unknown>> {
  return request("/api/research/requests", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, query, depth: "standard", purpose, category: category ?? (purpose === "opportunity" ? "business-opportunity" : "general"), schedule_id: scheduleId }),
  });
}

export function proposeWorldPulseSource(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request("/api/world-pulse/sources", { method: "POST", body: JSON.stringify(payload) });
}

export function createWorldPulseSchedule(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request("/api/world-pulse/schedules", { method: "POST", body: JSON.stringify(payload) });
}

export function updateWorldPulseSchedule(scheduleId: string, status: "planned" | "paused"): Promise<Record<string, unknown>> {
  return request(`/api/world-pulse/schedules/${scheduleId}`, { method: "PATCH", body: JSON.stringify({ status }) });
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

export function createOpportunityCycle(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request("/api/opportunity-cycles", { method: "POST", body: JSON.stringify(payload) });
}

export function updateOpportunityCycle(cycleId: string, status: "active" | "paused"): Promise<Record<string, unknown>> {
  return request(`/api/opportunity-cycles/${cycleId}`, { method: "PATCH", body: JSON.stringify({ status }) });
}

export function runOpportunityCycle(cycleId: string): Promise<Record<string, unknown>> {
  return request(`/api/opportunity-cycles/${cycleId}/run`, { method: "POST" });
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

export function addAcademyMaterial(courseId: string, payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request(`/api/academy/courses/${courseId}/materials`, { method: "POST", body: JSON.stringify(payload) });
}

export function addAcademyAssessment(courseId: string, payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request(`/api/academy/courses/${courseId}/assessments`, { method: "POST", body: JSON.stringify(payload) });
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

export function getVoiceStatus(): Promise<Record<string, unknown>> {
  return request("/api/voice/status");
}

export function interruptVoice(): Promise<Record<string, unknown>> {
  return request("/api/voice/interrupt", { method: "POST" });
}

export function pollAgentFleet(): Promise<Record<string, unknown>> {
  return request("/api/fleet/poll", { method: "POST" });
}

export function runContainmentDrill(agentId: string): Promise<Record<string, unknown>> {
  return request(`/api/fleet/agents/${agentId}/containment-drill`, { method: "POST" });
}

export function controlFleetAgent(
  agentId: string,
  action: "pause_capability" | "resume_capability" | "quarantine" | "recover",
  capability: string | null,
  reason: string,
): Promise<Record<string, unknown>> {
  return request(`/api/fleet/agents/${agentId}/control`, {
    method: "POST",
    body: JSON.stringify({ action, capability, reason }),
  });
}

export function executeFleetControl(approvalId: string): Promise<Record<string, unknown>> {
  return request(`/api/fleet/controls/${approvalId}/execute`, { method: "POST" });
}

export function createFleetLearning(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request("/api/fleet/learning", { method: "POST", body: JSON.stringify(payload) });
}

export function executeFleetLearning(approvalId: string): Promise<Record<string, unknown>> {
  return request(`/api/fleet/learning/${approvalId}/execute`, { method: "POST" });
}

export function requestFleetLearningRollback(updateId: string, reason: string): Promise<Record<string, unknown>> {
  return request(`/api/fleet/learning/${updateId}/rollback`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function executeFleetLearningRollback(approvalId: string): Promise<Record<string, unknown>> {
  return request(`/api/fleet/learning-rollbacks/${approvalId}/execute`, { method: "POST" });
}

export function resolveFleetIncident(incidentId: string): Promise<Record<string, unknown>> {
  return request(`/api/fleet/incidents/${incidentId}/resolve`, { method: "POST" });
}

export function requestEncryptedBackup(): Promise<Record<string, unknown>> {
  return request("/api/operations/backups", { method: "POST" });
}

export function executeEncryptedBackup(approvalId: string): Promise<Record<string, unknown>> {
  return request(`/api/operations/backups/${approvalId}/execute`, { method: "POST" });
}

export function requestRestoreDrill(): Promise<Record<string, unknown>> {
  return request("/api/operations/restore-drill", { method: "POST" });
}

export function executeRestoreDrill(approvalId: string): Promise<Record<string, unknown>> {
  return request(`/api/operations/restore-drill/${approvalId}/execute`, { method: "POST" });
}

export function searchWorkspace(query: string): Promise<{ query: string; results: Array<Record<string, unknown>> }> {
  return request(`/api/search?q=${encodeURIComponent(query)}`);
}
