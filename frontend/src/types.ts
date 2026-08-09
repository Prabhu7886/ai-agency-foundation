export type Workspace = { id: string; label: string; description: string };
export type Project = {
  id: string;
  name: string;
  description: string;
  root_path: string;
  repository_url?: string | null;
  status: string;
  task_count?: number;
  tasks?: Task[];
  updated_at: string;
};
export type Task = {
  id: string;
  project_id: string;
  title: string;
  prompt: string;
  status: string;
  risk_level: string;
  assigned_agent?: string | null;
  result_summary?: string | null;
  prompt_compilation?: {
    id: string;
    original_prompt: string;
    compiled_prompt: string;
    objective: string;
    data_classification: string;
    risk_level: string;
    approvals_required: string[];
    success_evidence: string[];
    compiler_mode: string;
    model?: string | null;
    created_at: string;
  } | null;
  updated_at: string;
};
export type Agent = {
  id: string;
  name: string;
  role: string;
  description: string;
  model_policy: string;
  status: string;
  prompt_version: string;
  capabilities: string[];
  skills: Array<{ id: string; name: string; category: string; version: string; status: string }>;
};
export type Skill = {
  id: string;
  name: string;
  category: string;
  description: string;
  version: string;
  status: string;
  risk_level: string;
  capabilities: string[];
};
export type Plugin = {
  id: string;
  name: string;
  category: string;
  description: string;
  status: string;
  connection_status: string;
  requires_approval: boolean;
  data_policy: string;
  capabilities: string[];
};
export type Approval = {
  id: string;
  action: string;
  summary: string;
  risk_level: string;
  status: string;
  evidence: Record<string, unknown>;
  execution?: { status: "running" | "completed" | "failed"; result_summary: string; started_at: string; finished_at?: string | null } | null;
  requested_at: string;
};
export type Activity = {
  id: number;
  event_type: string;
  summary: string;
  security_level: string;
  created_at: string;
};
export type WorldPulseItem = {
  headline: string;
  summary: string;
  source_url?: string | null;
  domain?: string | null;
  confidence: number;
  verification_state: string;
};
export type Bootstrap = {
  brand: { name: string; descriptor: string; motto: string; creed: string };
  workspaces: Workspace[];
  overview: {
    projects: number;
    agents: number;
    pending_approvals: number;
    open_tasks: number;
    opportunity_allocation: { existing: number; exploration: number };
  };
  projects: Project[];
  agents: Agent[];
  skills: Skill[];
  plugins: Plugin[];
  approvals: Approval[];
  world_pulse: WorldPulseItem[];
  opportunities: Array<Record<string, unknown>>;
  solutions: Array<Record<string, unknown>>;
  activity: Activity[];
  foundation: Record<string, unknown>;
  local_model: { available: boolean; model: string; endpoint: string; error?: string };
};
