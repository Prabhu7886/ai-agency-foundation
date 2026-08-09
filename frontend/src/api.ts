import type { Bootstrap, Project } from "./types";

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

export function chat(projectId: string, message: string): Promise<{
  answer: string;
  provider: string;
  error?: string;
}> {
  return request("/api/chat", { method: "POST", body: JSON.stringify({ project_id: projectId, message }) });
}

export function requestResearch(projectId: string | null, query: string): Promise<Record<string, unknown>> {
  return request("/api/research/requests", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, query, depth: "standard" }),
  });
}
