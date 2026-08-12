import { FormEvent, KeyboardEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AppWindow,
  Archive,
  ArchiveRestore,
  ArrowUpRight,
  AudioLines,
  Bot,
  BrainCircuit,
  Check,
  ChevronRight,
  CircleGauge,
  Code2,
  Copy,
  Database,
  FileCode2,
  FlaskConical,
  FolderGit2,
  Globe2,
  Layers3,
  LockKeyhole,
  Menu,
  MessageSquareText,
  Mic,
  Network,
  PackagePlus,
  PanelLeftClose,
  Plus,
  Radar,
  RotateCcw,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Square,
  Target,
  TerminalSquare,
  Trash2,
  UserRoundCheck,
  Workflow,
  X,
  Zap,
} from "lucide-react";
import { BrandMark } from "./components/BrandMark";
import {
  archiveConversation,
  bootstrap,
  changePlugin,
  chat,
  createAgent,
  createAcademyCourse,
  createLearningMemory,
  createOpportunity,
  createProject,
  createSolution,
  createWorldPulseSchedule,
  createSkill,
  deleteConversation,
  decideApproval,
  executeCodexDeviceLogin,
  executeCodexTask,
  executeDataJob,
  executeFleetControl,
  executeFleetLearning,
  executeFleetLearningRollback,
  executeResearch,
  executeGitHubOperation,
  executeSolutionTransition,
  getCodexStatus,
  getConversation,
  controlFleetAgent,
  createFleetLearning,
  requestCodexDeviceLogin,
  requestCodexTask,
  requestResearch,
  proposeWorldPulseSource,
  requestGitHubOperation,
  requestDataJob,
  requestFleetLearningRollback,
  requestSolutionTransition,
  restoreConversation,
  runSecurityScan,
  pollAgentFleet,
  resolveFleetIncident,
  updateAcademyCourse,
  decideLearningMemory,
  speakVoice,
  streamChat,
  transcribeVoice,
} from "./api";
import type { Agent, AgentIncident, Approval, Bootstrap, CodexStatus, Conversation, ConversationMessage, GitHubAction, GitHubGovernance, GitHubStatus, IndependentAgent, Plugin, Project, SecurityScan, Skill, Workspace, WorldPulseItem } from "./types";

const workspaceIcons: Record<string, ReactNode> = {
  "executive-home": <CircleGauge size={17} />,
  "ai-workspace": <BrainCircuit size={17} />,
  "agent-fleet": <Network size={17} />,
  "world-pulse": <Globe2 size={17} />,
  "opportunity-engine": <Target size={17} />,
  "solution-factory": <FlaskConical size={17} />,
  "approval-center": <UserRoundCheck size={17} />,
  "security-sentinel": <ShieldCheck size={17} />,
  "aegis-hub": <AudioLines size={17} />,
  "data-lab": <Database size={17} />,
};

function timeAgo(value: string) {
  const elapsed = Math.max(0, Date.now() - new Date(value).getTime());
  const minutes = Math.floor(elapsed / 60000);
  if (minutes < 1) return "now";
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function relativeTime(value: string) {
  const elapsed = timeAgo(value);
  return elapsed === "now" ? elapsed : `${elapsed} ago`;
}

function StatusPill({ children, tone = "neutral" }: { children: ReactNode; tone?: string }) {
  return <span className={`status-pill status-pill--${tone}`}>{children}</span>;
}

function EmptyState({ icon, title, body, action }: { icon: ReactNode; title: string; body: string; action?: ReactNode }) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon">{icon}</div>
      <h3>{title}</h3>
      <p>{body}</p>
      {action}
    </div>
  );
}

export default function App() {
  const [data, setData] = useState<Bootstrap | null>(null);
  const [activeWorkspace, setActiveWorkspace] = useState("executive-home");
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [createMode, setCreateMode] = useState<"project" | "agent" | "skill" | null>(null);
  const [fleetTab, setFleetTab] = useState<"agents" | "performance" | "tasks" | "skills" | "security" | "learning" | "plugins">("agents");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [codexLogin, setCodexLogin] = useState<{ verificationUrl: string; userCode: string } | null>(null);

  const refresh = async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const next = await bootstrap();
      setData(next);
      setSelectedProjectId((current) => current ?? next.projects[0]?.id ?? null);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Aegis failed to initialize");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const selectedProject = useMemo(
    () => data?.projects.find((project) => project.id === selectedProjectId) ?? data?.projects[0] ?? null,
    [data, selectedProjectId],
  );
  const workspace = data?.workspaces.find((item) => item.id === activeWorkspace);

  const mutate = async (operation: () => Promise<unknown>, success: string) => {
    setBusy(true);
    try {
      await operation();
      setToast(success);
      setCreateMode(null);
    } catch (reason) {
      setToast(reason instanceof Error ? reason.message : "Action failed");
    } finally {
      await refresh(true);
      setBusy(false);
    }
  };

  const decideAndExecute = async (item: Approval, decision: "approved" | "declined") => {
    await mutate(async () => {
      await decideApproval(item.id, decision);
      if (decision === "approved" && item.action === "public_web_research") {
        return executeResearch(item.id);
      }
      if (decision === "approved" && item.action === "github_operation") {
        return executeGitHubOperation(item.id);
      }
      if (decision === "approved" && item.action === "codex_device_login") {
        const result = await executeCodexDeviceLogin(item.id);
        setCodexLogin({ verificationUrl: result.verificationUrl, userCode: result.userCode });
        return result;
      }
      if (decision === "approved" && item.action === "codex_task") {
        return executeCodexTask(item.id);
      }
      if (decision === "approved" && item.action === "data_lab_job") {
        return executeDataJob(item.id);
      }
      if (decision === "approved" && item.action === "solution_transition") {
        return executeSolutionTransition(item.id);
      }
      if (decision === "approved" && item.action === "agent_recovery") {
        return executeFleetControl(item.id);
      }
      if (decision === "approved" && item.action === "agent_learning_deploy") {
        return executeFleetLearning(item.id);
      }
      if (decision === "approved" && item.action === "agent_learning_rollback") {
        return executeFleetLearningRollback(item.id);
      }
      return undefined;
    }, decision === "approved" && item.action === "public_web_research"
      ? "Research completed and report saved"
      : decision === "approved" && item.action === "github_operation"
        ? "Approved GitHub operation completed"
        : decision === "approved" && item.action === "codex_device_login"
          ? "Secure Codex sign-in is ready"
          : decision === "approved" && item.action === "codex_task"
            ? "Approved Codex task completed"
        : `Approval ${decision}`);
  };

  if (loading) {
    return (
      <div className="launch-screen">
        <BrandMark />
        <div className="launch-line"><span /></div>
        <p>Verifying the local foundation…</p>
      </div>
    );
  }

  if (!data || error) {
    return (
      <div className="launch-screen launch-screen--error">
        <BrandMark />
        <ShieldCheck size={34} />
        <h2>Aegis stopped safely</h2>
        <p>{error ?? "The encrypted foundation is unavailable."}</p>
        <button className="primary-button" onClick={() => void refresh()}>Retry startup audit</button>
      </div>
    );
  }

  return (
    <div className={`app-shell ${sidebarOpen ? "" : "app-shell--collapsed"}`}>
      <aside className="sidebar">
        <div className="sidebar__brand">
          <BrandMark compact={!sidebarOpen} />
          <button className="icon-button collapse-button" onClick={() => setSidebarOpen((value) => !value)} aria-label="Toggle sidebar">
            <PanelLeftClose size={17} />
          </button>
        </div>

        <button className="new-project-button" onClick={() => setCreateMode("project")}>
          <Plus size={17} /> <span>New project</span>
        </button>

        <nav className="workspace-nav" aria-label="Aegis workspaces">
          {data.workspaces.map((item) => (
            <button
              key={item.id}
              className={activeWorkspace === item.id ? "active" : ""}
              onClick={() => setActiveWorkspace(item.id)}
              title={item.label}
            >
              {workspaceIcons[item.id]} <span>{item.label}</span>
              {item.id === "approval-center" && data.overview.pending_approvals > 0 && (
                <b>{data.overview.pending_approvals}</b>
              )}
            </button>
          ))}
        </nav>

        <div className="project-list">
          <div className="sidebar-label"><span>Projects</span><FolderGit2 size={14} /></div>
          {data.projects.map((project) => (
            <button
              key={project.id}
              className={selectedProject?.id === project.id ? "active" : ""}
              onClick={() => {
                setSelectedProjectId(project.id);
                setActiveWorkspace("executive-home");
              }}
              title={project.name}
            >
              <span className="project-glyph">{project.name.slice(0, 1).toUpperCase()}</span>
              <span className="project-copy"><strong>{project.name}</strong><small>{project.task_count ?? 0} tasks</small></span>
            </button>
          ))}
        </div>

        <div className="sidebar__footer">
          <div className={`model-indicator ${data.local_model.available ? "online" : "offline"}`}>
            <span />
            <div><strong>{data.local_model.routing_enabled ? "Llama · DeepSeek · Qwen" : data.local_model.model}</strong><small>{data.local_model.available ? data.local_model.routing_enabled ? "Auto routing · one local model" : data.local_model.gpu_accelerated ? "RTX accelerated · local" : "CPU local · slower" : "Local model offline"}</small></div>
          </div>
        </div>
      </aside>

      <main className="main-stage">
        <header className="topbar">
          <button className="icon-button mobile-menu" onClick={() => setSidebarOpen((value) => !value)}><Menu size={18} /></button>
          <div>
            <div className="eyebrow">AEGIS / {selectedProject?.name ?? "NO PROJECT"}</div>
            <h1>{workspace?.label}</h1>
          </div>
          <div className="topbar__actions">
            <StatusPill tone="safe"><LockKeyhole size={12} /> Local only</StatusPill>
            <button className="icon-button" title="Search this workspace"><Search size={17} /></button>
            <button className="icon-button" title="Workspace settings"><Settings2 size={17} /></button>
          </div>
        </header>

        <section className="workspace-stage">
          {activeWorkspace === "executive-home" && (
            <ExecutiveHome
              data={data}
              project={selectedProject}
              onChat={(message) => mutate(() => chat(selectedProject!.id, message), "Aegis completed the local turn")}
              onGitHub={(payload) => mutate(() => requestGitHubOperation(payload), "GitHub operation sent to Approval Center")}
              onCodexLogin={() => mutate(() => requestCodexDeviceLogin(), "Codex sign-in sent to Approval Center")}
              onCodexTask={(message) => mutate(() => requestCodexTask(selectedProject!.id, message), "Codex task sent to Approval Center")}
              onCodexCheck={async () => {
                const status = await getCodexStatus();
                setToast(status.authenticated ? "Codex ChatGPT connection verified" : "Codex is installed but still needs secure sign-in");
                await refresh(true);
                return status;
              }}
            />
          )}
          {activeWorkspace === "ai-workspace" && <AIWorkspace project={selectedProject} conversations={data.conversations} onRefresh={() => refresh(true)} />}
          {activeWorkspace === "agent-fleet" && (
            <AgentFleet
              data={data}
              tab={fleetTab}
              onTab={setFleetTab}
              onCreate={setCreateMode}
              onPlugin={(plugin) => mutate(() => changePlugin(plugin.id, plugin.status !== "enabled"), plugin.status === "enabled" ? "Plugin disabled" : "Plugin approval created")}
              onPoll={() => mutate(() => pollAgentFleet(), "Independent agents checked")}
              onControl={(agentId, action, capability, reason) => mutate(() => controlFleetAgent(agentId, action, capability, reason), action === "recover" || action === "resume_capability" ? "Recovery sent to Approval Center" : "Agent containment applied")}
              onLearning={(payload) => mutate(() => createFleetLearning(payload), "Learning update evaluated and recorded")}
              onRollback={(updateId) => mutate(() => requestFleetLearningRollback(updateId, "Owner requested rollback from Agent Fleet"), "Learning rollback sent to Approval Center")}
              onResolve={(incidentId) => mutate(() => resolveFleetIncident(incidentId), "Incident marked resolved")}
            />
          )}
          {activeWorkspace === "world-pulse" && (
            <WorldPulse data={data} project={selectedProject} onResearch={(query, category, scheduleId) => mutate(() => requestResearch(selectedProject?.id ?? null, query, "world_pulse", category, scheduleId), "Research request sent to Approval Center")} onCreateSource={(payload) => mutate(() => proposeWorldPulseSource(payload), "Source proposal sent to Security & Operations approvals")} onCreateSchedule={(payload) => mutate(() => createWorldPulseSchedule(payload), "Approval-gated research schedule saved")} />
          )}
          {activeWorkspace === "opportunity-engine" && <OpportunityEngine data={data} project={selectedProject} onResearch={(query) => mutate(() => requestResearch(selectedProject?.id ?? null, query, "opportunity"), "Opportunity research sent to Approval Center")} onCreate={(payload) => mutate(() => createOpportunity(payload), "Opportunity scored from explicit evidence")} onSendToFactory={(payload) => mutate(() => createSolution(payload), "Opportunity sent to Solution Factory")} />}
          {activeWorkspace === "solution-factory" && <><SolutionCreateForm onCreate={(payload) => mutate(() => createSolution(payload), "Solution program created at discovery stage")} /><SolutionFactory data={data} onTransition={(id, stage, proof) => mutate(() => requestSolutionTransition(id, stage, proof), "Stage transition sent to Business & Creative approvals")} /></>}
          {activeWorkspace === "approval-center" && (
            <ApprovalCenter approvals={data.approvals} onDecision={decideAndExecute} />
          )}
          {activeWorkspace === "security-sentinel" && <SecuritySentinel data={data} project={selectedProject} />}
          {activeWorkspace === "aegis-hub" && <AegisHub data={data} onCreateCourse={(payload) => mutate(() => createAcademyCourse(payload), "Course added to Aegis Academy")} onUpdateCourse={(id, status, progress) => mutate(() => updateAcademyCourse(id, status, progress), "Learning progress updated")} onCreateMemory={(payload) => mutate(() => createLearningMemory(payload), "Preference saved under controlled learning")} onMemoryDecision={(id, status) => mutate(() => decideLearningMemory(id, status), "Learning preference updated")} />}
          {activeWorkspace === "data-lab" && <DataLab project={selectedProject} onRequest={(payload) => mutate(() => requestDataJob(payload), "Data cleaning plan sent to Approval Center")} />}
        </section>
      </main>

      {createMode && (
        <CreatePanel
          mode={createMode}
          busy={busy}
          onClose={() => setCreateMode(null)}
          onSubmit={(payload) => {
            if (createMode === "project") return mutate(() => createProject(payload as Parameters<typeof createProject>[0]), "Project workspace created");
            if (createMode === "agent") return mutate(() => createAgent(payload as Parameters<typeof createAgent>[0]), "Agent proposal created");
            return mutate(() => createSkill(payload as Parameters<typeof createSkill>[0]), "Skill proposal created");
          }}
        />
      )}
      {codexLogin && (
        <div className="codex-login-backdrop" role="dialog" aria-modal="true" aria-label="Secure Codex sign-in">
          <section className="codex-login-card">
            <button className="icon-button codex-login-close" onClick={() => setCodexLogin(null)} aria-label="Close sign-in"><X size={17} /></button>
            <div className="entity-icon agent"><Code2 size={20} /></div>
            <div className="eyebrow">OPENAI SECURE DEVICE LOGIN</div>
            <h2>Connect Codex to your ChatGPT account</h2>
            <p>Open the official sign-in page and enter this one-time code. Aegis never receives or stores your password.</p>
            <code>{codexLogin.userCode}</code>
            <a className="primary-button" href={codexLogin.verificationUrl} target="_blank" rel="noreferrer">Open secure sign-in <ArrowUpRight size={14} /></a>
            <button className="secondary-button" disabled={busy} onClick={() => void (async () => {
              setBusy(true);
              try {
                const status = await getCodexStatus();
                if (status.authenticated) {
                  setCodexLogin(null);
                  setToast("Codex ChatGPT connection verified");
                  await refresh(true);
                } else {
                  setToast("Sign-in is not complete yet");
                }
              } catch (reason) {
                setToast(reason instanceof Error ? reason.message : "Codex connection check failed");
              } finally { setBusy(false); }
            })()}>{busy ? "Checking…" : "I signed in — verify connection"}</button>
            <small>Credentials remain managed by the official Codex CLI. Coding turns still require individual Aegis approval.</small>
          </section>
        </div>
      )}
      {toast && <div className="toast"><Check size={16} />{toast}</div>}
    </div>
  );
}

function AIWorkspace({ project, conversations, onRefresh }: { project: Project | null; conversations: Conversation[]; onRefresh: () => Promise<void> }) {
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [streamStatus, setStreamStatus] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const conversationEnd = useRef<HTMLDivElement | null>(null);
  const skipNextConversationLoad = useRef(false);
  const allProjectConversations = useMemo(
    () => conversations.filter((item) => item.project_id === project?.id),
    [conversations, project?.id],
  );
  const projectConversations = allProjectConversations.filter((item) => item.status === "active");
  const archivedConversations = allProjectConversations.filter((item) => item.status === "archived");
  const displayedConversations = showArchived ? archivedConversations : projectConversations;
  const currentConversation = allProjectConversations.find((item) => item.id === selectedConversationId) ?? null;

  useEffect(() => {
    setSelectedConversationId(projectConversations[0]?.id ?? null);
    setMessages([]);
    setMessage("");
    setShowArchived(false);
  }, [project?.id]);

  useEffect(() => {
    if (!selectedConversationId) {
      setMessages([]);
      return;
    }
    if (skipNextConversationLoad.current) {
      skipNextConversationLoad.current = false;
      return;
    }
    let cancelled = false;
    setLoadingConversation(true);
    void getConversation(selectedConversationId)
      .then((item) => { if (!cancelled) setMessages(item.messages ?? []); })
      .catch((reason) => { if (!cancelled) setStreamStatus(reason instanceof Error ? reason.message : "Conversation failed to load"); })
      .finally(() => { if (!cancelled) setLoadingConversation(false); });
    return () => { cancelled = true; };
  }, [selectedConversationId]);

  useEffect(() => {
    conversationEnd.current?.scrollIntoView({ behavior: sending ? "auto" : "smooth", block: "end" });
  }, [messages, sending, streamStatus]);

  const newChat = () => {
    if (sending) return;
    setShowArchived(false);
    setSelectedConversationId(null);
    setMessages([]);
    setMessage("");
    setStreamStatus("");
  };

  const sendMessage = async (request: string) => {
    if (!project || sending) return;
    setSending(true);
    setStreamStatus("Opening encrypted local stream");
    const now = new Date().toISOString();
    const optimisticUserId = `pending-user-${crypto.randomUUID()}`;
    const optimisticAssistantId = `pending-assistant-${crypto.randomUUID()}`;
    let resolvedConversationId = selectedConversationId;
    setMessages((current) => [...current, {
      id: optimisticUserId,
      conversation_id: selectedConversationId ?? "pending",
      role: "user",
      content: request,
      provider: "owner",
      token_count: 0,
      created_at: now,
    }, {
      id: optimisticAssistantId,
      conversation_id: selectedConversationId ?? "pending",
      role: "assistant",
      content: "",
      provider: "ollama-local",
      token_count: 0,
      created_at: now,
      streaming: true,
    }]);
    try {
      await streamChat(project.id, request, selectedConversationId, (event) => {
        if (event.type === "start") {
          if (event.conversation) {
            resolvedConversationId = event.conversation.id;
            if (event.conversation.id !== selectedConversationId) {
              skipNextConversationLoad.current = true;
              setSelectedConversationId(event.conversation.id);
            }
          }
          if (event.user_message) {
            setMessages((current) => current.map((item) => item.id === optimisticUserId ? event.user_message! : item));
          }
          setStreamStatus(event.status ?? "Compiling request");
        } else if (event.type === "status") {
          setStreamStatus(event.status ?? "Thinking locally");
        } else if (event.type === "routing" && event.routing) {
          setStreamStatus(event.status ?? `${event.routing.label} selected`);
          setMessages((current) => current.map((item) => item.id === optimisticAssistantId ? { ...item, model: event.routing!.model } : item));
        } else if (event.type === "compilation" && event.compilation) {
          setMessages((current) => current.map((item) => item.id === optimisticAssistantId ? { ...item, compilation: event.compilation } : item));
        } else if (event.type === "token" && event.content) {
          setStreamStatus("Aegis is responding");
          setMessages((current) => current.map((item) => item.id === optimisticAssistantId ? { ...item, content: item.content + event.content } : item));
        } else if ((event.type === "done" || event.type === "error") && event.assistant_message) {
          setMessages((current) => current.map((item) => item.id === optimisticAssistantId ? event.assistant_message! : item));
          setStreamStatus(event.type === "error"
            ? event.detail ?? "Local stream failed safely"
            : event.timings
              ? `Ready in ${(event.timings.total_ms / 1000).toFixed(1)}s · rewrite ${(event.timings.prompt_rewrite_ms / 1000).toFixed(1)}s · first token ${event.timings.first_token_ms === null ? "n/a" : `${(event.timings.first_token_ms / 1000).toFixed(1)}s`}`
              : "");
        }
      });
      await onRefresh();
      if (resolvedConversationId) {
        const saved = await getConversation(resolvedConversationId);
        setMessages(saved.messages ?? []);
      }
    } catch (reason) {
      const error = reason instanceof Error ? reason.message : "Unknown local error";
      setMessages((current) => current.map((item) => item.id === optimisticAssistantId ? {
        ...item,
        content: item.content || "Aegis stopped safely before execution.",
        provider: "none",
        error,
        streaming: false,
      } : item));
      setStreamStatus(error);
    } finally {
      setSending(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const request = message.trim();
    if (!request || !project || sending) return;
    setMessage("");
    await sendMessage(request);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };

  const copyAnswer = async (item: ConversationMessage) => {
    await navigator.clipboard.writeText(item.content);
    setCopiedId(item.id);
    window.setTimeout(() => setCopiedId(null), 1500);
  };

  const regenerate = async () => {
    const lastOwnerMessage = [...messages].reverse().find((item) => item.role === "user");
    if (!lastOwnerMessage || sending) return;
    await sendMessage(lastOwnerMessage.content);
  };

  const archiveCurrent = async () => {
    if (!selectedConversationId || sending) return;
    await archiveConversation(selectedConversationId);
    const next = projectConversations.find((item) => item.id !== selectedConversationId);
    setSelectedConversationId(next?.id ?? null);
    setMessages([]);
    await onRefresh();
  };

  const restoreCurrent = async () => {
    if (!selectedConversationId || sending) return;
    await restoreConversation(selectedConversationId);
    setShowArchived(false);
    await onRefresh();
  };

  const deleteCurrent = async () => {
    if (!selectedConversationId || currentConversation?.status !== "archived" || sending) return;
    if (!window.confirm("Permanently delete this encrypted conversation? This cannot be undone.")) return;
    await deleteConversation(selectedConversationId);
    const next = archivedConversations.find((item) => item.id !== selectedConversationId);
    setSelectedConversationId(next?.id ?? null);
    setMessages([]);
    await onRefresh();
  };

  return <div className="ai-workspace ai-workspace--threads">
    <aside className="ai-thread-sidebar"><header><div>{showArchived ? <Archive size={15} /> : <MessageSquareText size={15} />}<strong>{showArchived ? "Archived" : "Conversations"}</strong></div><button title="New encrypted chat" onClick={newChat}><Plus size={15} /></button></header><div className="ai-thread-list">{displayedConversations.length === 0 ? <p>{showArchived ? "No archived conversations." : "No saved conversations yet."}</p> : displayedConversations.map((item) => <button className={`${item.id === selectedConversationId ? "active" : ""} ${item.status === "archived" ? "archived" : ""}`} key={item.id} onClick={() => setSelectedConversationId(item.id)}><strong>{item.title}</strong><span>{item.message_count} messages · {timeAgo(item.updated_at)}</span><small>{item.preview || "Encrypted local conversation"}</small></button>)}</div><footer><div><LockKeyhole size={12} /> SQLCipher encrypted</div><button className={showArchived ? "active" : ""} onClick={() => { const nextMode = !showArchived; const nextItems = nextMode ? archivedConversations : projectConversations; setShowArchived(nextMode); setSelectedConversationId(nextItems[0]?.id ?? null); setMessages([]); }}><Archive size={11} /> {archivedConversations.length}</button></footer></aside>
    <div className="ai-chat-main">
      <header className="ai-workspace__header"><div><div className="eyebrow"><BrainCircuit size={13} /> AEGIS CONVERSATION</div><h2>{currentConversation?.title ?? project?.name ?? "AI Workspace"}</h2><p>Streaming local reasoning with bounded encrypted history.</p></div><div className="ai-chat-controls"><StatusPill tone="safe">Auto-route · Llama / DeepSeek / Qwen</StatusPill>{currentConversation?.status === "archived" ? <><button className="chat-utility" onClick={() => void restoreCurrent()}><ArchiveRestore size={14} /> Restore</button><button className="chat-utility chat-utility--danger" onClick={() => void deleteCurrent()}><Trash2 size={14} /> Delete</button></> : selectedConversationId ? <button className="chat-utility" disabled={sending} onClick={() => void archiveCurrent()}><Archive size={14} /> Archive</button> : null}<button className="chat-utility" disabled={sending} onClick={newChat}><Plus size={14} /> New chat</button></div></header>
      <section className="ai-conversation">
        {loadingConversation ? <div className="ai-message ai-message--aegis ai-message--thinking"><div className="ai-avatar ai-avatar--aegis"><BrainCircuit size={14} /></div><div><span>Aegis</span><div className="ai-thinking"><i /><i /><i /> Decrypting local conversation…</div></div></div> : messages.length === 0 ? <div className="ai-welcome"><div className="ai-welcome__mark"><BrainCircuit size={30} /></div><h3>What are we building?</h3><p>Discuss an idea, analyze a market, make a plan, or prepare a coding task. Every turn is rewritten into a bounded execution contract, routed to the best local specialist, and saved only in the encrypted local database.</p><div className="model-route-grid"><span>Llama<small>General</small></span><span>DeepSeek<small>Coding</small></span><span>Qwen<small>Research · analysis</small></span></div><div className="ai-starters">{["Turn my idea into a practical plan", "Analyze a business opportunity", "Help me design a secure feature"].map((starter) => <button key={starter} onClick={() => setMessage(starter)}>{starter}<ChevronRight size={13} /></button>)}</div></div> : messages.map((item) => <article className="ai-turn" key={item.id}>
          <div className={`ai-message ${item.role === "user" ? "ai-message--owner" : "ai-message--aegis"}`}><div className={`ai-avatar ${item.role === "user" ? "ai-avatar--owner" : "ai-avatar--aegis"}`}>{item.role === "user" ? "S" : <BrainCircuit size={14} />}</div><div className={item.role === "assistant" ? "ai-response" : ""}><span>{item.role === "user" ? "You" : "Aegis"} · {item.model ?? item.provider ?? "local"} · {new Date(item.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span>{item.content ? <p>{item.content}{item.streaming && <i className="stream-cursor" />}</p> : item.streaming ? <div className="ai-thinking"><i /><i /><i /> {streamStatus || "Thinking locally…"}</div> : null}{item.error && <small>{item.error}</small>}{item.role === "assistant" && item.content && <div className="ai-message-actions"><button onClick={() => void copyAnswer(item)} title="Copy response">{copiedId === item.id ? <Check size={13} /> : <Copy size={13} />} {copiedId === item.id ? "Copied" : "Copy"}</button></div>}</div></div>
          {item.compilation && <details className="prompt-contract ai-contract"><summary><Sparkles size={11} /> View rewritten execution contract · {item.compilation.risk_level} risk</summary><div><label>Objective</label><p>{item.compilation.objective}</p><label>Compiled prompt</label><pre>{item.compilation.compiled_prompt}</pre><footer><span>{item.compilation.compiler_mode}{item.compilation.rewrite_duration_ms ? ` · ${(item.compilation.rewrite_duration_ms / 1000).toFixed(1)}s rewrite` : ""}</span>{item.compilation.model_routing && <span>{item.compilation.model_routing.label} · {item.compilation.model_routing.resource_fit.replaceAll("_", " ")}</span>}<span>{item.compilation.data_classification}</span></footer></div></details>}
        </article>)}
        {streamStatus && !sending && <div className="ai-stream-status">{streamStatus}</div>}
        <div ref={conversationEnd} />
      </section>
      {currentConversation?.status === "archived" ? <div className="ai-archived-actions"><Archive size={15} /><span>This encrypted conversation is read-only.</span><button onClick={() => void restoreCurrent()}><ArchiveRestore size={14} /> Restore conversation</button></div> : <div className="ai-composer-dock">{messages.length > 0 && <button className="regenerate-button" disabled={sending} onClick={() => void regenerate()}><RotateCcw size={13} /> Regenerate last response</button>}<form className="ai-composer" onSubmit={submit}><textarea rows={2} value={message} onChange={(event) => setMessage(event.target.value)} onKeyDown={handleKeyDown} placeholder="Message Aegis…" /><footer><div><LockKeyhole size={13} /> Encrypted history · Live local tokens · Enter to send</div><button aria-label="Send message" disabled={!message.trim() || !project || sending}><Send size={16} /></button></footer></form><small className="ai-disclaimer">Aegis can make mistakes. Verify important business, security, and financial decisions.</small></div>}
    </div>
  </div>;
}

function ExecutiveHome({ data, project, onChat, onGitHub, onCodexLogin, onCodexTask, onCodexCheck }: {
  data: Bootstrap;
  project: Project | null;
  onChat: (message: string) => Promise<void>;
  onGitHub: (payload: Parameters<typeof requestGitHubOperation>[0]) => Promise<void>;
  onCodexLogin: () => Promise<void>;
  onCodexTask: (message: string) => Promise<void>;
  onCodexCheck: () => Promise<CodexStatus>;
}) {
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!message.trim() || !project) return;
    setSending(true);
    const value = message;
    setMessage("");
    await onChat(value);
    setSending(false);
  };
  const governance = useMemo(() => {
    const completed = data.approvals.find((item) => item.evidence.operation === "inspect_governance" && item.execution?.status === "completed");
    if (!completed?.execution?.result_summary) return null;
    try { return JSON.parse(completed.execution.result_summary) as GitHubGovernance; } catch { return null; }
  }, [data.approvals]);
  return (
    <div className="dashboard-grid">
      <section className="hero-card span-8">
        <div className="hero-card__glow" />
        <div className="eyebrow"><Sparkles size={13} /> EXECUTIVE SIGNAL</div>
        <h2>See clearly.<br /><span>Act decisively.</span></h2>
        <p>{data.brand.creed}</p>
        <div className="hero-card__status"><span className="live-dot" /> Foundation controls inherited · Cloud private data blocked</div>
      </section>
      <section className="metric-stack span-4">
        <Metric label="Active projects" value={data.overview.projects} icon={<FolderGit2 />} />
        <Metric label="Ready agents" value={data.overview.agents} icon={<Bot />} />
        <Metric label="Pending decisions" value={data.overview.pending_approvals} icon={<UserRoundCheck />} accent />
        <Metric label="Open tasks" value={data.overview.open_tasks} icon={<Workflow />} />
      </section>

      <section className="panel span-8 project-room">
        <PanelHeader icon={<FolderGit2 size={17} />} title={project?.name ?? "Select a project"} action={<StatusPill tone="safe">Registered workspace</StatusPill>} />
        {project ? (
          <>
            <p className="muted project-description">{project.description}</p>
            <div className="project-meta"><code>{project.root_path}</code>{project.repository_url && <a href={project.repository_url} target="_blank" rel="noreferrer">GitHub <ArrowUpRight size={12} /></a>}</div>
            <div className="task-thread-list">
              {(project.tasks ?? []).length ? project.tasks!.slice(0, 5).map((task) => (
                <div className="task-thread" key={task.id}>
                  <div className={`task-state task-state--${task.status}`}><MessageSquareText size={15} /></div>
                  <div className="task-copy">
                    <strong>{task.title}</strong>
                    <small>{task.assigned_agent ?? "Aegis"} · {timeAgo(task.updated_at)}</small>
                    {task.prompt_compilation && (
                      <details className="prompt-contract">
                        <summary><Sparkles size={11} /> Prompt compiled · {task.prompt_compilation.risk_level} risk</summary>
                        <div>
                          <label>Original request</label>
                          <p>{task.prompt_compilation.original_prompt}</p>
                          <label>Execution contract</label>
                          <pre>{task.prompt_compilation.compiled_prompt}</pre>
                          <footer>
                            <span>{task.prompt_compilation.compiler_mode}</span>
                            <span>{task.prompt_compilation.data_classification}</span>
                          </footer>
                        </div>
                      </details>
                    )}
                    {task.result_summary && <p className="task-result">{task.result_summary}</p>}
                  </div>
                  <StatusPill tone={task.status === "completed" ? "safe" : task.status === "failed" ? "danger" : "neutral"}>{task.status}</StatusPill>
                </div>
              )) : <EmptyState icon={<MessageSquareText />} title="Start the first task" body="Discuss, plan, or build inside this registered project." />}
            </div>
            <form className="command-composer" onSubmit={submit}>
              <textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Ask Aegis to analyze, plan, or build…" rows={2} />
              <div><span><LockKeyhole size={13} /> Local model first</span><button aria-label="Send to Aegis" disabled={sending || !message.trim()}><Send size={16} /></button></div>
            </form>
          </>
        ) : <EmptyState icon={<FolderGit2 />} title="No project selected" body="Create a project workspace to begin." />}
      </section>

      <section className="panel span-4">
        <PanelHeader icon={<Activity size={17} />} title="Live activity" />
        <div className="activity-list">
          {data.activity.slice(0, 7).map((item) => (
            <div key={item.id}><span /><p>{item.summary}<small>{timeAgo(item.created_at)} · {item.security_level}</small></p></div>
          ))}
        </div>
      </section>
      <GitHubMaintenance
        project={project}
        status={data.integrations.github}
        connectionStatus={data.plugins.find((item) => item.id === "plugin-github")?.connection_status ?? "not_connected"}
        governance={governance}
        onRequest={onGitHub}
      />
      <CodexEngineering
        project={project}
        status={data.integrations.codex}
        connectionStatus={data.plugins.find((item) => item.id === "plugin-codex")?.connection_status ?? "not_connected"}
        onLogin={onCodexLogin}
        onTask={onCodexTask}
        onCheck={onCodexCheck}
      />
    </div>
  );
}

function GitHubMaintenance({ project, status, connectionStatus, governance, onRequest }: {
  project: Project | null;
  status: GitHubStatus;
  connectionStatus: string;
  governance: GitHubGovernance | null;
  onRequest: (payload: Parameters<typeof requestGitHubOperation>[0]) => Promise<void>;
}) {
  const [action, setAction] = useState<GitHubAction>("verify_auth");
  const [branch, setBranch] = useState(status.git?.branch?.startsWith("codex/") ? status.git.branch : "codex/aegis-next");
  const [paths, setPaths] = useState("");
  const [message, setMessage] = useState("Update Aegis controlled maintenance");
  const [title, setTitle] = useState("Update Aegis controlled maintenance");
  const [body, setBody] = useState("## Summary\n\nApproval-gated Aegis maintenance update.\n\n## Validation\n\n- Tests required before review");
  const [base, setBase] = useState("main");
  const [submitting, setSubmitting] = useState(false);
  const operations: Array<[GitHubAction, string]> = [
    ["verify_auth", "Verify"], ["inspect_governance", "Governance"], ["create_branch", "Branch"], ["stage_files", "Stage"],
    ["commit", "Commit"], ["push", "Push"], ["draft_pr", "Draft PR"],
  ];
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!project || submitting) return;
    const payload: Parameters<typeof requestGitHubOperation>[0] = { project_id: project.id, action };
    if (["create_branch", "push", "draft_pr"].includes(action)) payload.branch = branch.trim();
    if (action === "stage_files") payload.paths = paths.split(/[\n,]+/).map((item) => item.trim()).filter(Boolean);
    if (action === "commit") payload.message = message.trim();
    if (action === "inspect_governance") payload.base = base.trim();
    if (action === "draft_pr") Object.assign(payload, { title: title.trim(), body: body.trim(), base: "main" });
    setSubmitting(true);
    try { await onRequest(payload); } finally { setSubmitting(false); }
  };
  const needsBranch = ["create_branch", "push", "draft_pr"].includes(action);
  return <section className="panel span-12 github-maintenance">
    <PanelHeader icon={<TerminalSquare size={17} />} title="GitHub controlled maintenance" action={<StatusPill tone={connectionStatus === "connected" ? "safe" : "warning"}>{connectionStatus.replaceAll("_", " ")}</StatusPill>} />
    <div className="github-status-grid">
      <article><span>CLI</span><strong>{status.installed ? "Installed" : "Unavailable"}</strong></article>
      <article><span>Branch</span><strong>{status.git?.branch || "Unknown"}</strong></article>
      <article><span>Working tree</span><strong>{status.git?.clean ? "Clean" : "Changes present"}</strong></article>
      <article><span>Registered origin</span><strong>{status.git?.origin_matches_registered ? "Matched" : "Blocked"}</strong></article>
    </div>
    <div className="github-operation-tabs">{operations.map(([value, label]) => <button key={value} type="button" className={action === value ? "active" : ""} onClick={() => setAction(value)}>{label}</button>)}</div>
    <form className="github-operation-form" onSubmit={submit}>
      {needsBranch && <label>Protected branch<input required pattern="codex/.+" value={branch} onChange={(event) => setBranch(event.target.value)} /></label>}
      {action === "inspect_governance" && <label>Base branch<input required pattern="[A-Za-z0-9._/-]+" value={base} onChange={(event) => setBase(event.target.value)} /></label>}
      {action === "stage_files" && <label>Project-relative files<textarea required rows={3} value={paths} onChange={(event) => setPaths(event.target.value)} placeholder="aegis_core/api.py&#10;frontend/src/App.tsx" /></label>}
      {action === "commit" && <label>Commit message<input required value={message} onChange={(event) => setMessage(event.target.value)} /></label>}
      {action === "draft_pr" && <><label>Pull request title<input required value={title} onChange={(event) => setTitle(event.target.value)} /></label><label>Pull request body<textarea required rows={5} value={body} onChange={(event) => setBody(event.target.value)} /></label></>}
      <div className="github-operation-policy"><ShieldCheck size={16} /><span>Creates a single-use approval request. No merge, delete, force-push, arbitrary shell, or unregistered repository access is available.</span></div>
      <button className="primary-button" disabled={!project || submitting || status.git?.origin_matches_registered !== true}>{submitting ? "Requesting approval…" : `Request ${operations.find(([value]) => value === action)?.[1]}`}</button>
    </form>
    {governance && <div className="governance-snapshot">
      <PanelHeader icon={<ShieldCheck size={16} />} title="Last approved governance snapshot" action={<StatusPill tone={governance.protection.state === "protected" ? "safe" : "warning"}>{governance.protection.state.replaceAll("_", " ")}</StatusPill>} />
      <div className="github-status-grid">
        <article><span>Base branch</span><strong>{governance.base_branch}</strong></article>
        <article><span>Required reviews</span><strong>{governance.protection.required_approving_reviews}</strong></article>
        <article><span>Required checks</span><strong>{new Set([...governance.protection.required_checks, ...governance.protection.required_check_integrations]).size}</strong></article>
        <article><span>Admin enforcement</span><strong>{governance.protection.enforce_admins ? "On" : "Off"}</strong></article>
        <article><span>Current PR</span><strong>{governance.pull_request.found ? `#${governance.pull_request.number}${governance.pull_request.is_draft ? " · draft" : ""}` : "Not found"}</strong></article>
        <article><span>PR checks</span><strong>{governance.pull_request.found ? `${governance.pull_request.checks_total ?? 0} total · ${governance.pull_request.checks_failing ?? 0} failing` : "Unavailable"}</strong></article>
        <article><span>Review decision</span><strong>{governance.pull_request.review_decision ?? "None"}</strong></article>
        <article><span>Merge state</span><strong>{governance.pull_request.merge_state ?? "Unknown"}</strong></article>
      </div>
      {governance.pull_request.checks?.length ? <div className="governance-checks">{governance.pull_request.checks.map((check) => <span key={`${check.name}-${check.state}`}><i className={check.state === "SUCCESS" ? "passed" : ""} />{check.name} · {check.state}</span>)}</div> : null}
    </div>}
  </section>;
}

function CodexEngineering({ project, status, connectionStatus, onLogin, onTask, onCheck }: {
  project: Project | null;
  status: CodexStatus;
  connectionStatus: string;
  onLogin: () => Promise<void>;
  onTask: (message: string) => Promise<void>;
  onCheck: () => Promise<CodexStatus>;
}) {
  const [runtimeStatus, setRuntimeStatus] = useState(status);
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  useEffect(() => setRuntimeStatus(status), [status]);
  const check = async () => {
    setSubmitting(true);
    try { setRuntimeStatus(await onCheck()); } finally { setSubmitting(false); }
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const request = message.trim();
    if (!project || !request || submitting) return;
    setSubmitting(true);
    try { await onTask(request); setMessage(""); } finally { setSubmitting(false); }
  };
  return <section className="panel span-12 github-maintenance codex-engineering">
    <PanelHeader icon={<Code2 size={17} />} title="Codex internal engineering" action={<StatusPill tone={runtimeStatus.authenticated ? "safe" : "warning"}>{runtimeStatus.authenticated ? "ChatGPT connected" : connectionStatus.replaceAll("_", " ")}</StatusPill>} />
    <div className="github-status-grid">
      <article><span>Official CLI</span><strong>{runtimeStatus.installed ? "Installed" : "Unavailable"}</strong></article>
      <article><span>Protocol</span><strong>{runtimeStatus.protocol || "app-server-stdio"}</strong></article>
      <article><span>Authentication</span><strong>{runtimeStatus.authenticated ? runtimeStatus.plan_type || "Connected" : "Owner sign-in required"}</strong></article>
      <article><span>Turn boundary</span><strong>Approval · registered root</strong></article>
    </div>
    <div className="codex-connection-actions">
      <button className="secondary-button" disabled={!runtimeStatus.installed || submitting} onClick={() => void check()}>{submitting ? "Checking…" : "Check connection"}</button>
      <button className="secondary-button" disabled={!runtimeStatus.installed || runtimeStatus.authenticated || submitting} onClick={() => void onLogin()}>Request secure sign-in</button>
    </div>
    <form className="github-operation-form codex-task-form" onSubmit={submit}>
      <label>Engineering request<textarea required rows={4} value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Describe a coding task for this registered project. Aegis rewrites it before approval." /></label>
      <div className="github-operation-policy"><ShieldCheck size={16} /><span>Every Codex turn uses the rewritten execution contract, a single registered project root, workspace-write sandboxing, no network, and a separate owner approval.</span></div>
      <button className="primary-button" disabled={!project || !runtimeStatus.authenticated || !message.trim() || submitting}>{submitting ? "Working…" : "Request Codex task"}</button>
    </form>
  </section>;
}

function Metric({ label, value, icon, accent = false }: { label: string; value: number; icon: ReactNode; accent?: boolean }) {
  return <div className={`metric-card ${accent ? "metric-card--accent" : ""}`}><span>{icon}</span><div><strong>{value}</strong><small>{label}</small></div></div>;
}

function PanelHeader({ icon, title, action }: { icon: ReactNode; title: string; action?: ReactNode }) {
  return <div className="panel-header"><div>{icon}<h3>{title}</h3></div>{action}</div>;
}

type FleetTab = "agents" | "performance" | "tasks" | "skills" | "security" | "learning" | "plugins";

function fleetTone(agent: IndependentAgent) {
  if (agent.snapshot.controls?.quarantined || agent.open_incidents > 0) return "warning";
  return agent.bridge.last_status === "healthy" || agent.bridge.last_status === "degraded" ? "safe" : "neutral";
}

function AgentFleet({ data, tab, onTab, onCreate, onPlugin, onPoll, onControl, onLearning, onRollback, onResolve }: {
  data: Bootstrap;
  tab: FleetTab;
  onTab: (tab: FleetTab) => void;
  onCreate: (mode: "agent" | "skill") => void;
  onPlugin: (plugin: Plugin) => void;
  onPoll: () => Promise<void>;
  onControl: (agentId: string, action: "pause_capability" | "resume_capability" | "quarantine" | "recover", capability: string | null, reason: string) => Promise<void>;
  onLearning: (payload: Record<string, unknown>) => Promise<void>;
  onRollback: (updateId: string) => Promise<void>;
  onResolve: (incidentId: string) => Promise<void>;
}) {
  const [learning, setLearning] = useState({
    agent_id: data.agent_fleet[0]?.id ?? "",
    course_id: "",
    title: "",
    source: "",
    content: "",
    risk_level: "low",
  });
  const tabs: FleetTab[] = ["agents", "performance", "tasks", "skills", "security", "learning", "plugins"];
  const submitLearning = async (event: FormEvent) => {
    event.preventDefault();
    await onLearning({ ...learning, course_id: learning.course_id || null });
    setLearning({ ...learning, title: "", source: "", content: "" });
  };
  return (
    <div className="single-workspace">
      <div className="workspace-intro"><div><div className="eyebrow">SUPERVISED INDEPENDENCE</div><h2>Agents run their business cycles.<br /><span>Aegis protects the system.</span></h2><p>Authenticated local monitoring, capability-level containment, reviewable learning, and rollback without merging agent runtimes.</p></div><Network className="intro-icon" /></div>
      <div className="fleet-toolbar"><div className="segmented-tabs fleet-tabs">{tabs.map((item) => <button key={item} className={tab === item ? "active" : ""} onClick={() => onTab(item)}>{item}</button>)}</div><button className="secondary-button" onClick={() => void onPoll()}><RotateCcw size={14} /> Check now</button></div>

      {tab === "agents" && <div className="card-grid">{data.agent_fleet.map((agent) => {
        const connected = agent.bridge.last_status !== "offline";
        const paused = agent.snapshot.controls?.paused_capabilities ?? [];
        return <article className="entity-card fleet-agent-card" key={agent.id}>
          <div className="entity-card__top"><div className="entity-icon agent"><Bot size={20} /></div><StatusPill tone={fleetTone(agent)}>{agent.snapshot.controls?.quarantined ? "quarantined" : agent.bridge.last_status}</StatusPill></div>
          <h3>{agent.name}</h3><span className="entity-subtitle">{agent.role}</span><p>{agent.description}</p>
          <div className="fleet-stat-row"><span><strong>{Number(agent.snapshot.metrics?.tasks_total ?? 0)}</strong> tasks</span><span><strong>{agent.open_incidents}</strong> incidents</span><span><strong>{paused.length}</strong> paused</span></div>
          <div className="chip-row">{(agent.snapshot.identity?.capabilities ?? agent.capabilities).slice(0, 5).map((item) => <span key={item}>{item}</span>)}</div>
          {agent.bridge.last_error && <small className="fleet-error">{agent.bridge.last_error}</small>}
          <div className="fleet-actions">{agent.bridge.dashboard_url && <a className="plugin-action" href={agent.bridge.dashboard_url}>Open independent studio <ChevronRight size={14} /></a>}<button disabled={!connected || agent.snapshot.controls?.quarantined} onClick={() => { if (window.confirm(`Quarantine ${agent.name}? Safe work will stop until recovery is approved.`)) void onControl(agent.id, "quarantine", null, "Owner initiated containment from Aegis Agent Fleet"); }}>Quarantine</button></div>
          <footer><span>Bridge v{agent.bridge.contract_version}</span><span>{agent.bridge.last_seen_at ? relativeTime(agent.bridge.last_seen_at) : "never seen"}</span></footer>
        </article>;
      })}{data.agent_fleet.length === 0 && <EmptyState icon={<Bot />} title="No independent agents registered" body="Register an authenticated loopback Agent Bridge before supervision begins." />}</div>}

      {tab === "performance" && <div className="fleet-panel-grid">{data.agent_fleet.map((agent) => {
        const metrics = agent.snapshot.metrics;
        return <section className="panel fleet-panel" key={agent.id}><PanelHeader icon={<Activity size={17} />} title={agent.name} /><div className="fleet-kpis"><div><strong>{metrics?.tasks_total ?? 0}</strong><span>Recorded tasks</span></div><div><strong>{Math.round(Number(metrics?.failure_rate ?? 0) * 100)}%</strong><span>Failure rate</span></div><div><strong>{metrics?.resources?.rss_mb ?? 0} MB</strong><span>Bridge memory</span></div></div><div className="fleet-domain-metrics">{Object.entries(metrics?.domain ?? {}).map(([key, value]) => <span key={key}><b>{value}</b>{key.replaceAll("_", " ")}</span>)}</div><small>Observed {agent.snapshot.observed_at ? relativeTime(agent.snapshot.observed_at) : "never"}. Metrics exclude private task payloads.</small></section>;
      })}</div>}

      {tab === "tasks" && <section className="panel"><PanelHeader icon={<Workflow size={17} />} title="Sanitized progress feed" /><div className="fleet-table"><div className="fleet-table__head"><span>Agent</span><span>Task</span><span>Status</span><span>Updated</span></div>{data.agent_fleet.flatMap((agent) => (agent.snapshot.tasks ?? []).map((task) => ({ agent, task }))).map(({ agent, task }) => <div key={`${agent.id}-${task.task_id}`}><span>{agent.name}</span><span>{task.task_type.replaceAll("_", " ")}</span><span><StatusPill tone={task.status === "completed" ? "safe" : task.status === "failed" ? "warning" : "neutral"}>{task.status}</StatusPill></span><span>{task.updated_at ? relativeTime(task.updated_at) : "—"}</span></div>)}</div><small>Only identifiers, state, and timestamps cross the bridge. Resume text, customer data, prompts, and credentials remain inside each agent.</small></section>}

      {tab === "skills" && <><CardGrid items={data.skills} render={(skill) => <SkillCard skill={skill} />} action={<button className="secondary-button" onClick={() => onCreate("skill")}><PackagePlus size={15} /> New Aegis skill</button>} /><div className="fleet-panel-grid">{data.agent_fleet.map((agent) => <section className="panel fleet-panel" key={agent.id}><PanelHeader icon={<Layers3 size={17} />} title={`${agent.name} reported skills`} /><div className="fleet-skill-list">{(agent.snapshot.skills ?? []).map((skill, index) => <span key={String(skill.skill_id ?? index)}><b>{String(skill.skill_id ?? "skill")}</b>v{String(skill.version ?? "unknown")}</span>)}</div></section>)}</div></>}

      {tab === "security" && <div className="fleet-security-layout"><section className="panel"><PanelHeader icon={<ShieldCheck size={17} />} title="Incident reports" />{data.agent_incidents.length === 0 ? <EmptyState icon={<ShieldCheck />} title="No agent incidents" body="Aegis has not detected a threshold-crossing security or reliability event." /> : <div className="incident-list">{data.agent_incidents.map((incident) => <IncidentCard key={incident.id} incident={incident} agent={data.agent_fleet.find((item) => item.id === incident.agent_id)} onControl={onControl} onResolve={onResolve} />)}</div>}</section><section className="panel"><PanelHeader icon={<Activity size={17} />} title="Containment ledger" /><div className="control-ledger">{data.agent_controls.slice(0, 30).map((control) => <div key={control.id}><StatusPill tone={control.outcome === "completed" ? "safe" : "warning"}>{control.outcome}</StatusPill><div><strong>{control.action.replaceAll("_", " ")}</strong><span>{control.agent_id} · {control.capability ?? "whole agent"} · {control.source}</span><small>{control.reason}</small></div></div>)}</div></section></div>}

      {tab === "learning" && <div className="fleet-learning-layout"><section className="panel"><PanelHeader icon={<BrainCircuit size={17} />} title="Prepare controlled learning update" /><form className="fleet-learning-form" onSubmit={submitLearning}><label>Target agent<select required value={learning.agent_id} onChange={(event) => setLearning({ ...learning, agent_id: event.target.value })}>{data.agent_fleet.map((agent) => <option value={agent.id} key={agent.id}>{agent.name}</option>)}</select></label><label>Completed course<select value={learning.course_id} onChange={(event) => { const course = data.academy_courses.find((item) => item.id === event.target.value); setLearning({ ...learning, course_id: event.target.value, source: course?.source_url ?? course?.provider ?? learning.source }); }}><option value="">No completed course — require approval</option>{data.academy_courses.filter((course) => course.status === "completed").map((course) => <option value={course.id} key={course.id}>{course.title}</option>)}</select></label><input required value={learning.title} onChange={(event) => setLearning({ ...learning, title: event.target.value })} placeholder="Knowledge or skill update title" /><input required value={learning.source} onChange={(event) => setLearning({ ...learning, source: event.target.value })} placeholder="Source course, URL, or owner reference" /><textarea required minLength={40} value={learning.content} onChange={(event) => setLearning({ ...learning, content: event.target.value })} placeholder="Verified lesson, operating rule, or bounded skill reference…" /><label>Risk<select value={learning.risk_level} onChange={(event) => setLearning({ ...learning, risk_level: event.target.value })}><option value="low">Low — may auto-deploy after all checks</option><option value="medium">Medium — owner approval</option><option value="high">High — owner approval</option><option value="critical">Critical — owner approval</option></select></label><button className="primary-button">Evaluate update</button><small>Only a low-risk update linked to a completed course, with no authority-expanding language, can auto-deploy. Every deployment is hashed, reported, and reversible.</small></form></section><section className="panel"><PanelHeader icon={<Archive size={17} />} title="Learning and rollback history" /><div className="learning-ledger">{data.agent_learning_updates.map((update) => <article key={update.id}><div><StatusPill tone={update.status === "deployed" ? "safe" : update.status === "failed" ? "warning" : "neutral"}>{update.status.replaceAll("_", " ")}</StatusPill><span>{update.risk_level} risk</span></div><h3>{update.title}</h3><p>{update.content_preview}</p><small>{update.agent_id} · SHA-256 {update.content_sha256.slice(0, 12)}… · {relativeTime(update.created_at)}</small>{update.status === "deployed" && <button onClick={() => void onRollback(update.id)}><RotateCcw size={13} /> Request rollback</button>}</article>)}</div></section></div>}

      {tab === "plugins" && <CardGrid items={data.plugins} render={(plugin) => <PluginCard plugin={plugin} onChange={() => onPlugin(plugin)} />} />}
    </div>
  );
}

function IncidentCard({ incident, agent, onControl, onResolve }: { incident: AgentIncident; agent?: IndependentAgent; onControl: (agentId: string, action: "pause_capability" | "resume_capability" | "quarantine" | "recover", capability: string | null, reason: string) => Promise<void>; onResolve: (incidentId: string) => Promise<void> }) {
  return <article className="incident-card"><header><StatusPill tone={incident.severity === "critical" || incident.severity === "high" ? "warning" : "neutral"}>{incident.severity}</StatusPill><span>{incident.status}</span><small>{relativeTime(incident.detected_at)}</small></header><h3>{incident.title}</h3><p>{incident.report.summary}</p><div className="incident-section"><strong>Action taken</strong><span>{String(incident.report.action_taken?.status ?? "monitor only").replaceAll("_", " ")}{incident.capability ? ` · ${incident.capability}` : ""}</span></div><details><summary>Evidence and possible solutions</summary><pre>{JSON.stringify(incident.report.evidence ?? {}, null, 2)}</pre><ol>{incident.report.possible_solutions?.map((item) => <li key={item}>{item}</li>)}</ol></details><div className="fleet-actions">{incident.status !== "resolved" && agent?.snapshot.controls?.quarantined && <button onClick={() => void onControl(incident.agent_id, "recover", null, `Recover after reviewing incident ${incident.id}`)}>Request recovery</button>}{incident.status !== "resolved" && incident.capability && agent?.snapshot.controls?.paused_capabilities?.includes(incident.capability) && <button onClick={() => void onControl(incident.agent_id, "resume_capability", incident.capability ?? null, `Resume after reviewing incident ${incident.id}`)}>Request capability resume</button>}{incident.status !== "resolved" && <button onClick={() => void onResolve(incident.id)}>Mark resolved</button>}</div></article>;
}

function CardGrid<T>({ items, render, action }: { items: T[]; render: (item: T) => ReactNode; action?: ReactNode }) {
  return <><div className="list-toolbar"><span>{items.length} registered</span>{action}</div><div className="card-grid">{items.map((item, index) => <div key={index}>{render(item)}</div>)}</div></>;
}

function AgentCard({ agent }: { agent: Agent }) {
  return <article className="entity-card"><div className="entity-card__top"><div className="entity-icon agent"><Bot size={20} /></div><StatusPill tone={agent.status === "ready" ? "safe" : "neutral"}>{agent.status}</StatusPill></div><h3>{agent.name}</h3><span className="entity-subtitle">{agent.role}</span><p>{agent.description}</p><div className="chip-row">{agent.skills.map((skill) => <span key={skill.id}>{skill.name}</span>)}</div><footer><span>{agent.model_policy}</span><span>{agent.prompt_version}</span></footer></article>;
}

function SkillCard({ skill }: { skill: Skill }) {
  return <article className="entity-card"><div className="entity-card__top"><div className="entity-icon skill"><Layers3 size={20} /></div><StatusPill tone={skill.status === "active" ? "safe" : "neutral"}>{skill.status}</StatusPill></div><h3>{skill.name}</h3><span className="entity-subtitle">{skill.category} · v{skill.version}</span><p>{skill.description}</p><div className="chip-row">{skill.capabilities.slice(0, 4).map((item) => <span key={item}>{item}</span>)}</div><footer><span>{skill.risk_level} risk</span><span>versioned</span></footer></article>;
}

function PluginCard({ plugin, onChange }: { plugin: Plugin; onChange: () => void }) {
  const enabled = plugin.status === "enabled";
  return <article className="entity-card plugin-card"><div className="entity-card__top"><div className="entity-icon plugin"><AppWindow size={20} /></div><StatusPill tone={enabled ? "safe" : plugin.status === "planned" ? "neutral" : "warning"}>{plugin.status}</StatusPill></div><h3>{plugin.name}</h3><span className="entity-subtitle">{plugin.category} · {plugin.connection_status.replaceAll("_", " ")}</span><p>{plugin.description}</p><div className="policy-line"><LockKeyhole size={13} /> {plugin.data_policy.replaceAll("_", " ")}</div><button className="plugin-action" disabled={plugin.status === "planned"} onClick={onChange}>{enabled ? "Disable" : "Request enable"}<ChevronRight size={14} /></button></article>;
}

function LegacyWorldPulse({ data, project, onResearch }: { data: Bootstrap; project: Project | null; onResearch: (query: string, category: string) => Promise<void> }) {
  const [query, setQuery] = useState("");
  const niches = ["all", "ai-technology", "markets-trades", "economy-trade", "us-politics", "global-affairs", "commodities", "public-figures"];
  const [niche, setNiche] = useState("all");
  const [reader, setReader] = useState<WorldPulseItem | null>(null);
  const items = niche === "all" ? data.world_pulse : data.world_pulse.filter((item) => String(item.category ?? "general").toLowerCase().replaceAll("_", "-").includes(niche) || (niche === "ai-technology" && /\b(ai|tech|software)\b/i.test(item.headline)));
  const submit = async (event: FormEvent) => { event.preventDefault(); if (!query.trim()) return; const value = query; setQuery(""); await onResearch(value, niche === "all" ? "general" : niche); };
  return <div className="single-workspace"><div className="workspace-intro pulse-intro"><div><div className="eyebrow">GLOBAL IMPACT INTELLIGENCE</div><h2>Signal over noise.<br /><span>Every claim earns its confidence.</span></h2><p>AI, IT, economies, conflicts, trade, gold, silver, politicians, insiders, and institutional holdings.</p></div><Radar className="intro-icon" /></div><form className="research-bar" onSubmit={submit}><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Research a public topic…" /><button disabled={!query.trim()}>Request research</button></form><div className="source-policy"><ShieldCheck size={16} /><span>Public queries only. Web access requires Approval Center authorization and an approved research session.</span></div>{data.world_pulse.length === 0 ? <EmptyState icon={<Globe2 />} title="World Pulse is protected and waiting" body={`No unverified headlines are displayed. Start an approved research task${project ? ` for ${project.name}` : ""}.`} /> : <div className="card-grid">{data.world_pulse.map((item, index) => <article className="entity-card pulse-card" key={index}><div className="pulse-card__meta"><StatusPill tone={String(item.verification_state) === "single_source" ? "neutral" : "safe"}>{String(item.verification_state ?? "unverified").replaceAll("_", " ")}</StatusPill><span>{Math.round(Number(item.confidence ?? 0) * 100)}% source confidence</span></div><h3>{String(item.headline)}</h3><p>{String(item.summary)}</p>{item.source_url && <a href={String(item.source_url)} target="_blank" rel="noreferrer">{String(item.domain ?? "Open source")} <ArrowUpRight size={12} /></a>}</article>)}</div>}</div>;
}

function WorldPulseControls({ data, onResearch, onCreateSource, onCreateSchedule }: {
  data: Bootstrap;
  onResearch: (query: string, category: string, scheduleId?: string) => Promise<void>;
  onCreateSource: (payload: Record<string, unknown>) => Promise<void>;
  onCreateSchedule: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const [schedule, setSchedule] = useState({ name: "", niche: "ai-technology", query: "", cadence_hours: 24 });
  const [source, setSource] = useState({ label: "", niche: "ai-technology", source_type: "publisher", locator: "", reason: "" });
  const submitSchedule = async (event: FormEvent) => { event.preventDefault(); await onCreateSchedule(schedule); setSchedule({ name: "", niche: "ai-technology", query: "", cadence_hours: 24 }); };
  const submitSource = async (event: FormEvent) => { event.preventDefault(); await onCreateSource({ ...source, identity_verified: false }); setSource({ label: "", niche: "ai-technology", source_type: "publisher", locator: "", reason: "" }); };
  return <section className="pulse-operations">
    <div className="pulse-operation-grid">
      <details className="panel"><summary><Plus size={13} /> Save research schedule</summary><form onSubmit={submitSchedule}><input required value={schedule.name} onChange={(event) => setSchedule({ ...schedule, name: event.target.value })} placeholder="Schedule name" /><input required value={schedule.query} onChange={(event) => setSchedule({ ...schedule, query: event.target.value })} placeholder="Bounded public query" /><select value={schedule.niche} onChange={(event) => setSchedule({ ...schedule, niche: event.target.value })}><option value="ai-technology">AI & technology</option><option value="markets-trades">Markets & trades</option><option value="economy-trade">Economy & trade</option><option value="us-politics">US politics</option><option value="global-affairs">Global affairs</option><option value="commodities">Commodities</option></select><label>Cadence (hours)<input type="number" min="1" max="720" value={schedule.cadence_hours} onChange={(event) => setSchedule({ ...schedule, cadence_hours: Number(event.target.value) })} /></label><button className="secondary-button">Save plan</button><small>Each run still creates a Security & Operations approval. No unattended network access is enabled.</small></form></details>
      <details className="panel"><summary><Plus size={13} /> Propose trusted source</summary><form onSubmit={submitSource}><input required value={source.label} onChange={(event) => setSource({ ...source, label: event.target.value })} placeholder="Publisher or public account" /><input required value={source.locator} onChange={(event) => setSource({ ...source, locator: event.target.value })} placeholder="Official URL or public handle" /><select value={source.source_type} onChange={(event) => setSource({ ...source, source_type: event.target.value })}><option value="publisher">Publisher</option><option value="public_account">Public account</option><option value="public_data">Public dataset</option></select><input required minLength={5} value={source.reason} onChange={(event) => setSource({ ...source, reason: event.target.value })} placeholder="Why should Aegis monitor it?" /><button className="secondary-button">Send for approval</button><small>Approval means the source may be monitored; it does not make every claim from that source true.</small></form></details>
    </div>
    {data.world_pulse_schedules.length > 0 && <div className="pulse-schedule-list">{data.world_pulse_schedules.map((item) => <article key={item.id}><div><strong>{item.name}</strong><span>{item.niche.replaceAll("-", " ")} · every {item.cadence_hours}h · {item.last_requested_at ? `requested ${timeAgo(item.last_requested_at)} ago` : "never requested"}</span></div><button onClick={() => void onResearch(item.query, item.niche, item.id)}>Request run now</button></article>)}</div>}
    {data.world_pulse_sources.length > 0 && <div className="approved-source-strip">{data.world_pulse_sources.map((item) => <span key={item.id}><StatusPill tone={item.status === "approved" ? "safe" : "warning"}>{item.status}</StatusPill>{item.label} · {item.source_type.replaceAll("_", " ")}</span>)}</div>}
  </section>;
}

function WorldPulse({ data, project, onResearch, onCreateSource, onCreateSchedule }: { data: Bootstrap; project: Project | null; onResearch: (query: string, category: string, scheduleId?: string) => Promise<void>; onCreateSource: (payload: Record<string, unknown>) => Promise<void>; onCreateSchedule: (payload: Record<string, unknown>) => Promise<void> }) {
  const niches = ["all", "ai-technology", "markets-trades", "economy-trade", "us-politics", "global-affairs", "commodities", "public-figures"];
  const [query, setQuery] = useState("");
  const [niche, setNiche] = useState("all");
  const [reader, setReader] = useState<WorldPulseItem | null>(null);
  const items = niche === "all" ? data.world_pulse : data.world_pulse.filter((item) => {
    const category = String(item.category ?? "general").toLowerCase().replaceAll("_", "-");
    return category.includes(niche) || (niche === "ai-technology" && /\b(ai|tech|software)\b/i.test(item.headline));
  });
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const value = query.trim();
    if (!value) return;
    setQuery("");
    await onResearch(value, niche === "all" ? "general" : niche);
  };
  return <div className="single-workspace">
    <div className="workspace-intro pulse-intro"><div><div className="eyebrow">VERIFIED WORLD INTELLIGENCE</div><h2>Signal over noise.<br /><span>Every claim earns its confidence.</span></h2><p>AI, markets, economies, trade, politics, conflicts, commodities, and approved public figures.</p></div><Radar className="intro-icon" /></div>
    <div className="niche-tabs">{niches.map((item) => <button key={item} className={niche === item ? "active" : ""} onClick={() => setNiche(item)}>{item.replaceAll("-", " ")}</button>)}</div>
    <form className="research-bar" onSubmit={submit}><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Research ${niche === "all" ? "a public topic" : niche.replaceAll("-", " ")}…`} /><button disabled={!query.trim()}>Request research</button></form>
    <div className="source-policy"><ShieldCheck size={16} /><span>Public queries only. Research requires approval; reporting, commentary, and social claims remain visibly distinct.</span></div>
    <WorldPulseControls data={data} onResearch={onResearch} onCreateSource={onCreateSource} onCreateSchedule={onCreateSchedule} />
    {items.length === 0 ? <EmptyState icon={<Globe2 />} title="No verified signals in this niche" body={`Start an approved research task${project ? ` for ${project.name}` : ""}. Aegis does not fill empty space with unverified headlines.`} /> : <div className="card-grid">{items.map((item, index) => <article className="entity-card pulse-card" key={item.id ?? index}><div className="pulse-card__meta"><StatusPill tone={item.verification_state === "single_source" ? "neutral" : "safe"}>{item.verification_state.replaceAll("_", " ")}</StatusPill><span>{Math.round(item.confidence * 100)}% confidence</span></div><small>{String(item.category ?? "general").replaceAll("-", " ")} · {String(item.region ?? "Global")}</small><h3>{item.headline}</h3><p>{item.summary}</p><button className="reader-button" onClick={() => setReader(item)}>Read inside Aegis <ChevronRight size={12} /></button></article>)}</div>}
    {reader && <div className="reader-backdrop" onMouseDown={() => setReader(null)}><aside className="pulse-reader" onMouseDown={(event) => event.stopPropagation()}><header><div><div className="eyebrow">AEGIS INTERNAL READER</div><h2>{reader.headline}</h2></div><button className="icon-button" onClick={() => setReader(null)}><X size={18} /></button></header><div className="reader-evidence"><StatusPill tone={reader.verification_state === "single_source" ? "warning" : "safe"}>{reader.verification_state.replaceAll("_", " ")}</StatusPill><span>{Math.round(reader.confidence * 100)}% source confidence</span></div><p>{reader.summary}</p><section><h3>Why it matters</h3><p>This brief is stored locally from an approved research session. Review the original before making a consequential decision.</p></section>{reader.source_url && <a className="primary-button" href={reader.source_url}>Open original in this tab <ArrowUpRight size={14} /></a>}</aside></div>}
  </div>;
}

function OpportunityCreateForm({ onCreate }: { onCreate: (payload: Record<string, unknown>) => Promise<void> }) {
  const [title, setTitle] = useState("");
  const [thesis, setThesis] = useState("");
  const [evidence, setEvidence] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    await onCreate({ title, thesis, allocation: "existing-80", evidence: [evidence], evidence_strength: 70, revenue_potential: 60, strategic_fit: 75, speed_to_revenue: 60, execution_risk: 40 });
    setTitle(""); setThesis(""); setEvidence("");
  };
  return <form className="research-bar workspace-action-form" onSubmit={submit}><Target size={18} /><input required value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Opportunity title" /><input required minLength={20} value={thesis} onChange={(event) => setThesis(event.target.value)} placeholder="Testable thesis" /><input required value={evidence} onChange={(event) => setEvidence(event.target.value)} placeholder="Evidence source or observation" /><button>Score</button></form>;
}

function SolutionCreateForm({ onCreate }: { onCreate: (payload: Record<string, unknown>) => Promise<void> }) {
  const [title, setTitle] = useState("");
  const [problem, setProblem] = useState("");
  const [audience, setAudience] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    await onCreate({ title, problem, audience });
    setTitle(""); setProblem(""); setAudience("");
  };
  return <form className="research-bar workspace-action-form" onSubmit={submit}><FlaskConical size={18} /><input required value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Solution name" /><input required minLength={20} value={problem} onChange={(event) => setProblem(event.target.value)} placeholder="Observed problem" /><input required value={audience} onChange={(event) => setAudience(event.target.value)} placeholder="Who has this problem?" /><button>Discover</button></form>;
}

function OpportunityEngine({ data, project, onResearch, onCreate, onSendToFactory }: {
  data: Bootstrap;
  project: Project | null;
  onResearch: (query: string) => Promise<void>;
  onCreate: (payload: Record<string, unknown>) => Promise<void>;
  onSendToFactory: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const reports = data.research_reports.filter((item) => item.purpose === "opportunity" && (!project || item.project_id === project.id));
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const value = query.trim();
    if (!value || submitting) return;
    setSubmitting(true);
    await onResearch(value);
    setQuery("");
    setSubmitting(false);
  };
  return <div className="single-workspace opportunity-workspace">
    <div className="workspace-intro"><div><div className="eyebrow">CAPITAL DISCIPLINE</div><h2>Research first.<br /><span>Invest after evidence.</span></h2><p>Aegis collects approved public evidence, labels source quality, writes an executive report, and only then lets an idea enter the scorecard.</p></div><Target className="intro-icon" /></div>
    <form className="research-bar opportunity-research" onSubmit={submit}><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Research a market, customer problem, or AI business opportunity…" /><button disabled={!query.trim() || submitting}>{submitting ? "Requesting…" : "Research opportunity"}</button></form>
    <div className="source-policy"><ShieldCheck size={16} /><span>Public sources only. Each run requires approval, blocks private/client data, records citations, and produces an encrypted local report.</span></div>
    <div className="opportunity-summary-grid"><div className="allocation-panel"><div className="allocation-ring"><span><strong>80 / 20</strong><small>allocation</small></span></div><div><h3>Existing businesses</h3><div className="allocation-bar"><i style={{ width: "80%" }} /></div><p>80% improves and monetizes what we already own.</p><h3>Exploration</h3><div className="allocation-bar exploration"><i style={{ width: "20%" }} /></div><p>20% tests new AI opportunities with strict stop criteria.</p></div></div><div className="opportunity-metrics"><article><strong>{reports.length}</strong><span>Research reports</span></article><article><strong>{data.opportunities.length}</strong><span>Scored opportunities</span></article><article><strong>{reports.reduce((total, item) => total + item.source_count, 0)}</strong><span>Accepted sources</span></article></div></div>
    <section className="opportunity-section"><PanelHeader icon={<Radar size={17} />} title="Opportunity research reports" action={<StatusPill tone={reports.length ? "safe" : "neutral"}>{reports.length} ready</StatusPill>} />
      {reports.length === 0 ? <EmptyState icon={<Radar />} title="No research report yet" body="Submit a public topic, approve it in Approval Center, and Aegis will return here with a source-backed executive report." /> : <div className="research-report-list">{reports.map((item) => <article className="research-report" key={item.id}><header><div><div className="eyebrow">PUBLIC RESEARCH · {new Date(item.created_at).toLocaleString()}</div><h3>{item.report.title}</h3></div><div className="report-badges"><StatusPill tone={item.report.quality_gate === "supported_discovery" ? "safe" : "warning"}>{item.report.quality_gate?.replaceAll("_", " ") ?? "legacy quality"}</StatusPill><StatusPill tone={Number(item.report.source_metrics.verified_page_count ?? 0) > 0 ? "safe" : "warning"}>{Number(item.report.source_metrics.verified_page_count ?? 0)} full pages</StatusPill><StatusPill tone={Number(item.report.source_metrics.unresolved_claim_count ?? 0) === 0 ? "safe" : "danger"}>{Number(item.report.source_metrics.corroborated_claim_count ?? 0)} corroborated · {Number(item.report.source_metrics.unresolved_claim_count ?? 0)} conflicts</StatusPill><StatusPill tone={item.independent_domains >= 2 ? "safe" : "warning"}>{item.source_count} sources · {item.independent_domains} domains</StatusPill></div></header><section><h4>Executive Summary</h4><ul>{item.report.executive_summary.map((line) => <li key={line}>{line}</li>)}</ul></section><section><h4>Key findings</h4><div className="report-findings">{item.report.key_findings.map((finding, index) => <article key={`${finding.headline}-${index}`}><div><StatusPill tone={finding.confidence >= .7 ? "safe" : "neutral"}>{Math.round(finding.confidence * 100)}% confidence</StatusPill><span>{finding.source_ids.join(", ")}</span></div><h5>{finding.headline}</h5><p>{finding.evidence}</p><small>{finding.implication}</small></article>)}</div></section><details><summary>Recommendations, claim checks, caveats, and sources</summary><div className="report-detail-grid"><section><h4>Recommended next steps</h4><ol>{item.report.recommended_next_steps.map((line) => <li key={line}>{line}</li>)}</ol></section><section><h4>Claim-level checks</h4><ul>{(item.report.claim_assessments ?? []).map((claim) => <li key={claim.id}><strong>{claim.status.replaceAll("_", " ")}</strong> · {claim.claim} · {claim.source_ids.join(", ")}{claim.metric_values.length ? ` · ${claim.metric_values.join(" vs ")}` : ""}</li>)}</ul></section><section><h4>Further questions</h4><ul>{item.report.further_questions.map((line) => <li key={line}>{line}</li>)}</ul></section><section><h4>Caveats</h4><ul>{item.report.caveats.map((line) => <li key={line}>{line}</li>)}</ul></section><section><h4>Sources</h4><div className="report-sources">{item.report.sources.map((source) => <a key={source.id} href={source.url} target="_blank" rel="noreferrer"><span>{source.id} · {source.domain} · {source.source_tier} · {source.freshness_state ?? "unknown date"} · {source.page_verification_state?.replaceAll("_", " ") ?? "legacy excerpt"}{source.methodology_terms?.length ? " · methodology signal" : ""}</span>{source.title}<ArrowUpRight size={12} /></a>)}</div></section></div></details></article>)}</div>}
    </section>
    <section className="opportunity-section"><PanelHeader icon={<CircleGauge size={17} />} title="Evidence-backed scorecard" action={<StatusPill>{data.opportunities.length} scored</StatusPill>} /><details className="manual-score"><summary><Plus size={13} /> Score a researched opportunity manually</summary><OpportunityCreateForm onCreate={onCreate} /></details>{data.opportunities.length === 0 ? <EmptyState icon={<Zap />} title="No unsupported promises" body="Score an opportunity only after the research report is reviewed and customer or pricing evidence is attached." /> : <div className="card-grid">{data.opportunities.map((item, index) => <article className="entity-card" key={index}><StatusPill tone="safe">{String(item.score)} / 100</StatusPill><h3>{String(item.title)}</h3><p>{String(item.thesis)}</p><small>{String(item.allocation)}</small><button className="plugin-action" onClick={() => void onSendToFactory({ opportunity_id: String(item.id), title: String(item.title), problem: String(item.thesis), audience: "Validated target customers" })}>Send to Solution Factory <ChevronRight size={14} /></button></article>)}</div>}</section>
  </div>;
}

function LegacySolutionFactory({ data, onCreate }: { data: Bootstrap; onCreate: (payload: Record<string, unknown>) => Promise<void> }) {
  void onCreate;
  const stages = ["Discover", "Verify", "Design", "Prototype", "Test", "Launch", "Learn"];
  return <div className="single-workspace"><div className="workspace-intro"><div><div className="eyebrow">PROBLEM → PROOF</div><h2>Create solutions<br /><span>people will actually use.</span></h2><p>Start with a real pain, prove demand, build the smallest useful answer, and measure reality.</p></div><FlaskConical className="intro-icon" /></div><div className="factory-flow">{stages.map((stage, index) => <div key={stage}><span>{index + 1}</span><strong>{stage}</strong>{index < stages.length - 1 && <ChevronRight size={16} />}</div>)}</div>{data.solutions.length === 0 ? <EmptyState icon={<BrainCircuit />} title="Factory floor is clear" body="A verified problem will become the first solution program." /> : <div className="card-grid">{data.solutions.map((item, index) => <article className="entity-card" key={index}><StatusPill>{String(item.stage)}</StatusPill><h3>{String(item.title)}</h3><p>{String(item.problem)}</p><small>{String(item.audience)}</small></article>)}</div>}</div>;
}

function SolutionFactory({ data, onTransition }: { data: Bootstrap; onTransition: (id: string, stage: string, proof: string) => Promise<void> }) {
  const stages = ["Discover", "Validate", "Prototype", "Pilot", "Scale"];
  const nextStage = (stage: string) => ({ discover: "validate", validate: "prototype", prototype: "pilot", pilot: "scale" } as Record<string, string>)[stage];
  return <div className="single-workspace">
    <div className="workspace-intro"><div><div className="eyebrow">PROBLEM → PROOF</div><h2>Create solutions<br /><span>people will actually use.</span></h2><p>Opportunity Engine discovers and scores. Solution Factory validates, builds, launches, and measures under owner approval.</p></div><FlaskConical className="intro-icon" /></div>
    <div className="factory-flow">{stages.map((stage, index) => <div key={stage}><span>{index + 1}</span><strong>{stage}</strong>{index < stages.length - 1 && <ChevronRight size={16} />}</div>)}</div>
    {data.solutions.length === 0 ? <EmptyState icon={<BrainCircuit />} title="Factory floor is clear" body="A verified problem will become the first solution program." /> : <div className="card-grid">{data.solutions.map((item, index) => { const next = nextStage(String(item.stage)); return <article className="entity-card" key={index}><StatusPill>{String(item.stage)}</StatusPill><h3>{String(item.title)}</h3><p>{String(item.problem)}</p><small>{String(item.audience)}{item.opportunity_id ? " · linked opportunity" : ""}</small>{next && <button className="plugin-action" onClick={() => { const proof = window.prompt(`Evidence required to advance to ${next}`); if (proof && proof.trim().length >= 10) void onTransition(String(item.id), next, proof.trim()); }}>Propose {next} <ChevronRight size={14} /></button>}</article>; })}</div>}
  </div>;
}

function LegacyApprovalCenter({ approvals, onDecision }: { approvals: Approval[]; onDecision: (item: Approval, decision: "approved" | "declined") => Promise<void> }) {
  const [runningId, setRunningId] = useState<string | null>(null);
  const pending = approvals.filter((item) => item.status === "pending");
  const decide = async (item: Approval, decision: "approved" | "declined") => {
    setRunningId(item.id);
    try {
      await onDecision(item, decision);
    } finally {
      setRunningId(null);
    }
  };
  return <div className="single-workspace"><div className="workspace-intro compact"><div><div className="eyebrow">HUMAN AUTHORITY</div><h2>Nothing consequential<br /><span>happens in the dark.</span></h2></div><UserRoundCheck className="intro-icon" /></div>{pending.length === 0 ? <EmptyState icon={<Check />} title="Approval queue is clear" body="Aegis will surface evidence, risk, cost, and exact scope before asking." /> : <div className="approval-list">{pending.map((item) => <article key={item.id}><div><StatusPill tone={item.risk_level === "high" || item.risk_level === "critical" ? "danger" : "warning"}>{item.risk_level} risk</StatusPill><span>{timeAgo(item.requested_at)}</span></div><h3>{item.summary}</h3><p>Action: {item.action.replaceAll("_", " ")}</p><pre>{JSON.stringify(item.evidence, null, 2)}</pre><footer><button className="decline-button" disabled={Boolean(runningId)} onClick={() => void decide(item, "declined")}><X size={15} /> Decline</button><button className="approve-button" disabled={Boolean(runningId)} onClick={() => void decide(item, "approved")}>{runningId === item.id ? <Activity size={15} /> : <Check size={15} />} {runningId === item.id && item.action === "public_web_research" ? "Researching…" : runningId === item.id && item.action === "codex_device_login" ? "Starting sign-in…" : runningId === item.id ? "Executing…" : ["public_web_research", "github_operation", "codex_device_login", "codex_task"].includes(item.action) ? "Approve & run" : "Approve"}</button></footer></article>)}</div>}</div>;
}

function ApprovalCenter({ approvals, onDecision }: { approvals: Approval[]; onDecision: (item: Approval, decision: "approved" | "declined") => Promise<void> }) {
  const [runningId, setRunningId] = useState<string | null>(null);
  const [queue, setQueue] = useState<"security_operations" | "business_creative">("security_operations");
  const pending = approvals.filter((item) => item.status === "pending");
  const visible = pending.filter((item) => (item.approval_queue ?? "security_operations") === queue);
  const decide = async (item: Approval, decision: "approved" | "declined") => { setRunningId(item.id); try { await onDecision(item, decision); } finally { setRunningId(null); } };
  const count = (name: string) => pending.filter((item) => (item.approval_queue ?? "security_operations") === name).length;
  return <div className="single-workspace">
    <div className="workspace-intro compact"><div><div className="eyebrow">OWNER AUTHORITY · ONE AUDIT LEDGER</div><h2>Two queues.<br /><span>One accountable decision trail.</span></h2></div><UserRoundCheck className="intro-icon" /></div>
    <div className="approval-queue-tabs"><button className={queue === "security_operations" ? "active" : ""} onClick={() => setQueue("security_operations")}><ShieldCheck size={15} /> Security & Operations <b>{count("security_operations")}</b></button><button className={queue === "business_creative" ? "active" : ""} onClick={() => setQueue("business_creative")}><Sparkles size={15} /> Business & Creative <b>{count("business_creative")}</b></button></div>
    {visible.length === 0 ? <EmptyState icon={<Check />} title={`${queue === "security_operations" ? "Security & Operations" : "Business & Creative"} queue is clear`} body="Aegis will show exact scope, evidence, risk, freshness, and intended action before asking." /> : <div className="approval-list">{visible.map((item) => <article key={item.id}><div><StatusPill tone={item.risk_level === "high" || item.risk_level === "critical" ? "danger" : "warning"}>{item.risk_level} risk</StatusPill><span>{timeAgo(item.requested_at)}</span></div><h3>{item.summary}</h3><p>Action: {item.action.replaceAll("_", " ")}</p><pre>{JSON.stringify(item.evidence, null, 2)}</pre><footer><button className="decline-button" disabled={Boolean(runningId)} onClick={() => void decide(item, "declined")}><X size={15} /> Decline</button><button className="approve-button" disabled={Boolean(runningId)} onClick={() => void decide(item, "approved")}>{runningId === item.id ? <Activity size={15} /> : <Check size={15} />} {runningId === item.id ? "Executing…" : ["public_web_research", "github_operation", "codex_device_login", "codex_task", "data_lab_job", "solution_transition"].includes(item.action) ? "Approve & run" : "Approve"}</button></footer></article>)}</div>}
  </div>;
}

function SecuritySentinel({ data, project }: { data: Bootstrap; project: Project | null }) {
  const [scan, setScan] = useState<SecurityScan | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const controls = [
    ["Local API", data.foundation.local_only, String(data.foundation.api_bind)],
    ["SQLCipher", data.foundation.sqlcipher_required, "required"],
    ["Chroma", !data.foundation.chroma_server_enabled, String(data.foundation.vector_store_mode)],
    ["Cloud privacy", data.foundation.cloud_private_data === "blocked", String(data.foundation.cloud_private_data)],
    ["Ollama", data.local_model.available && Boolean(data.local_model.gpu_accelerated), data.local_model.available ? `${data.local_model.model} · ${data.local_model.gpu_accelerated ? "RTX GPU" : "CPU fallback"}` : "offline"],
    ["External research", data.foundation.external_research === "approved_public_sessions", String(data.foundation.external_research)],
    ["GitHub maintenance", data.foundation.github_maintenance === "single_use_approval", String(data.foundation.github_maintenance)],
  ];
  const executeScan = async () => {
    if (!project || scanning) return;
    setScanning(true);
    setScanError(null);
    try {
      setScan(await runSecurityScan(project.id));
    } catch (reason) {
      setScanError(reason instanceof Error ? reason.message : "Local scan failed");
    } finally {
      setScanning(false);
    }
  };
  return <div className="single-workspace">
    <div className="workspace-intro security-intro"><div><div className="eyebrow">CONTINUOUS ASSURANCE</div><h2>Trust evidence.<br /><span>Verify everything.</span></h2><p>The foundation remains authoritative for encryption, local inference, data handling, approvals, and network boundaries.</p></div><ShieldCheck className="intro-icon" /></div>
    <div className="security-grid">{controls.map(([name, passed, detail]) => <article key={String(name)} className={passed ? "passed" : "guarded"}><span>{passed ? <Check /> : <LockKeyhole />}</span><div><h3>{String(name)}</h3><p>{String(detail)}</p></div></article>)}</div>
    <div className="panel policy-panel"><PanelHeader icon={<FileCode2 size={17} />} title="Inherited foundation" action={<StatusPill tone="safe">Enforced</StatusPill>} /><p>Every Aegis workspace, agent, skill, and plugin passes through the same SQLCipher, loopback, offline-mode, secret-redaction, and approval controls.</p></div>
    <section className="panel sentinel-scan">
      <PanelHeader icon={<Search size={17} />} title="Registered-project local scan" action={<button className="secondary-button" disabled={!project || scanning} onClick={() => void executeScan()}>{scanning ? "Scanning…" : "Run read-only scan"}</button>} />
      <p>Scans tracked text files for secret-shaped values and risky code patterns. It does not execute project code or contact an external vulnerability service.</p>
      {scanError && <div className="scan-error">{scanError}</div>}
      {scan && <>
        <div className="github-status-grid"><article><span>Status</span><strong>{scan.status}</strong></article><article><span>Files scanned</span><strong>{scan.files_scanned}</strong></article><article><span>Critical / high</span><strong>{scan.counts.critical} / {scan.counts.high}</strong></article><article><span>Medium</span><strong>{scan.counts.medium}</strong></article></div>
        {scan.findings.length ? <div className="security-findings">{scan.findings.map((finding, index) => <article key={`${finding.file}-${finding.line}-${finding.rule}-${index}`}><StatusPill tone={finding.severity === "critical" || finding.severity === "high" ? "danger" : "warning"}>{finding.severity}</StatusPill><div><strong>{finding.rule} · {finding.file}{finding.line ? `:${finding.line}` : ""}</strong><p>{finding.message}</p></div></article>)}</div> : <EmptyState icon={<Check />} title="No configured patterns matched" body="This is supporting evidence, not proof that the project has no vulnerabilities." />}
        <details className="scan-limitations"><summary>Dependency posture and limitations</summary><pre>{JSON.stringify({ dependency_posture: scan.dependency_posture, limitations: scan.limitations }, null, 2)}</pre></details>
      </>}
    </section>
  </div>;
}

function PrivateVoiceSession() {
  const [recording, setRecording] = useState(false);
  const [message, setMessage] = useState("Push to talk when you're ready.");
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const toggle = async () => {
    if (recording) {
      recorder.current?.stop(); stream.current?.getTracks().forEach((track) => track.stop()); setRecording(false); setMessage("Transcribing with the local speech engine…"); return;
    }
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
      recorder.current = new MediaRecorder(stream.current);
      chunks.current = [];
      recorder.current.ondataavailable = (event) => { if (event.data.size) chunks.current.push(event.data); };
      recorder.current.onstop = async () => {
        try {
          const result = await transcribeVoice(new Blob(chunks.current, { type: recorder.current?.mimeType || "audio/webm" }));
          setMessage(result.text || "No speech detected.");
          if (result.text) await speakVoice(`I heard: ${result.text}`);
        } catch (reason) { setMessage(reason instanceof Error ? reason.message : "Local transcription failed."); }
      };
      recorder.current.start(); setRecording(true); setMessage("Listening locally… nothing is being uploaded.");
    } catch { setMessage("Microphone permission was not granted."); }
  };
  return <div className="voice-workspace"><div className={`voice-orb ${recording ? "recording" : ""}`}><button onClick={() => void toggle()}>{recording ? <Square /> : <Mic />}</button><i /><i /><i /></div><div className="eyebrow">PRIVATE PUSH-TO-TALK</div><h2>{message}</h2><p>Audio goes only to the loopback Aegis API. Temporary recordings are deleted after local transcription; no cloud speech service is used.</p><StatusPill tone="safe"><LockKeyhole size={12} /> Local audio policy</StatusPill></div>;
}

function AegisHub({ data, onCreateCourse, onUpdateCourse, onCreateMemory, onMemoryDecision }: {
  data: Bootstrap;
  onCreateCourse: (payload: Record<string, unknown>) => Promise<void>;
  onUpdateCourse: (id: string, status: string, progress: number) => Promise<void>;
  onCreateMemory: (payload: Record<string, unknown>) => Promise<void>;
  onMemoryDecision: (id: string, status: "confirmed" | "disabled") => Promise<void>;
}) {
  const [tab, setTab] = useState<"identity" | "academy" | "voice" | "learning">("identity");
  const [course, setCourse] = useState({ title: "", provider: "Coursera", source_url: "", learning_goal: "" });
  const [preference, setPreference] = useState("");
  const submitCourse = async (event: FormEvent) => { event.preventDefault(); await onCreateCourse(course); setCourse({ title: "", provider: "Coursera", source_url: "", learning_goal: "" }); };
  const submitPreference = async (event: FormEvent) => { event.preventDefault(); if (!preference.trim()) return; await onCreateMemory({ kind: "explicit", category: "communication", statement: preference.trim(), reason: "Owner-supplied preference", confidence: 1, affects_authority: false }); setPreference(""); };
  return <div className="single-workspace hub-workspace">
    <div className="hub-hero"><img src="/aegis-avatar.png" alt="Aegis digital avatar" /><div><div className="eyebrow">OWNER-CONTROLLED DIGITAL PARTNER</div><h2>Aegis Hub</h2><p>Your always-digital executive partner for business conversation, private voice, shared courses, and transparent learning. Aegis can propose; you retain authority.</p><div className="chip-row"><span>Always digital</span><span>Local first</span><span>No silent retraining</span></div></div></div>
    <div className="segmented-tabs hub-tabs">{(["identity", "academy", "voice", "learning"] as const).map((item) => <button key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item}</button>)}</div>
    {tab === "identity" && <div className="hub-grid"><section className="panel"><PanelHeader icon={<Sparkles size={17} />} title="Digital identity" action={<StatusPill tone="safe">Owner controlled</StatusPill>} /><p>Professional, friendly, direct, factual, ambitious, and evidence-aware. Aegis never presents itself as human and never expands its own permissions.</p></section><section className="panel"><PanelHeader icon={<ShieldCheck size={17} />} title="Authority boundary" /><ul><li>Low-risk analysis and local organization may run directly.</li><li>External, sensitive, financial, publishing, and system-changing work requires approval.</li><li>Learning that changes authority is proposal-only and must pass evaluation.</li></ul></section></div>}
    {tab === "academy" && <div className="academy-layout"><form className="panel academy-form" onSubmit={submitCourse}><PanelHeader icon={<BrainCircuit size={17} />} title="Add a learning path" /><label>Course title<input required value={course.title} onChange={(event) => setCourse({ ...course, title: event.target.value })} placeholder="Course or subject" /></label><label>Provider<input required value={course.provider} onChange={(event) => setCourse({ ...course, provider: event.target.value })} placeholder="Coursera, edX, YouTube…" /></label><label>Public course link <span>optional</span><input value={course.source_url} onChange={(event) => setCourse({ ...course, source_url: event.target.value })} placeholder="Official or permitted course URL" /></label><label>Learning goal<textarea value={course.learning_goal} onChange={(event) => setCourse({ ...course, learning_goal: event.target.value })} placeholder="What should we be able to do after this?" /></label><button className="primary-button">Add to Academy</button><small>Credentials are not connected. Aegis stores only the course plan and public link until you approve an official integration.</small></form><section><div className="learning-cycle">Learn → Practice → Evaluate → Propose skill update → Approve → Release</div>{data.academy_courses.length === 0 ? <EmptyState icon={<BrainCircuit />} title="Academy is ready" body="Add a course and learn it with Aegis through notes, exercises, business applications, and review." /> : <div className="course-list">{data.academy_courses.map((item) => <article className="entity-card" key={item.id}><div className="entity-card__top"><StatusPill tone={item.status === "completed" ? "safe" : "neutral"}>{item.status}</StatusPill><span>{Math.round(item.progress)}%</span></div><h3>{item.title}</h3><p>{item.provider} · {item.learning_goal || "Goal not set"}</p><div className="progress-track"><i style={{ width: `${item.progress}%` }} /></div><footer>{item.source_url ? <a href={item.source_url} target="_blank" rel="noreferrer">Official course <ArrowUpRight size={12} /></a> : <span>Local plan</span>}<button onClick={() => void onUpdateCourse(item.id, item.progress >= 100 ? "completed" : "active", Math.min(100, item.progress + 10))}>+10%</button></footer></article>)}</div>}</section></div>}
    {tab === "voice" && <PrivateVoiceSession />}
    {tab === "learning" && <div className="learning-control"><form className="panel" onSubmit={submitPreference}><PanelHeader icon={<BrainCircuit size={17} />} title="Teach Aegis explicitly" /><p>Save a non-sensitive preference. Explicit presentation preferences apply directly; inferred or authority-changing changes remain proposals.</p><textarea value={preference} onChange={(event) => setPreference(event.target.value)} placeholder="Example: Give me a concise executive summary before technical detail." /><button className="primary-button" disabled={!preference.trim()}>Save preference</button></form><section className="memory-list">{data.learning_memory.length === 0 ? <EmptyState icon={<BrainCircuit />} title="No learned preferences yet" body="Aegis will keep each preference visible, editable, disableable, and attributable." /> : data.learning_memory.map((item) => <article className="entity-card" key={item.id}><div className="entity-card__top"><StatusPill tone={item.status === "confirmed" ? "safe" : item.status === "disabled" ? "neutral" : "warning"}>{item.status}</StatusPill><span>{item.kind} · {Math.round(item.confidence * 100)}%</span></div><h3>{item.category}</h3><p>{item.statement}</p><small>{item.reason}</small>{item.status === "proposed" && <footer><button onClick={() => void onMemoryDecision(item.id, "disabled")}>Disable</button><button onClick={() => void onMemoryDecision(item.id, "confirmed")}>Confirm</button></footer>}</article>)}</section></div>}
  </div>;
}

function DataLab({ project, onRequest }: { project: Project | null; onRequest: (payload: Record<string, unknown>) => Promise<void> }) {
  const [path, setPath] = useState("");
  const stages = [["01", "Preserve", "Keep an immutable raw copy"], ["02", "Profile", "Measure shape, types, gaps, and drift"], ["03", "Validate", "Apply explicit quality rules"], ["04", "Standardize", "Normalize formats without hiding changes"], ["05", "Deduplicate", "Propose matches with confidence"], ["06", "Approve", "Review repairs before publishing"], ["07", "Report", "Ship cleaned data with provenance"]];
  const submit = async (event: FormEvent) => { event.preventDefault(); if (!project) return; await onRequest({ project_id: project.id, source_path: path, operations: ["trim_strings", "normalize_nulls", "deduplicate"], required_columns: [] }); setPath(""); };
  return <div className="single-workspace"><div className="workspace-intro"><div><div className="eyebrow">DATA YOU CAN DEFEND</div><h2>Clean it.<br /><span>Keep the evidence.</span></h2><p>Raw data is never silently overwritten. Every transformation has lineage, confidence, and a QA report.</p></div><Database className="intro-icon" /></div><form className="research-bar" onSubmit={submit}><Database size={18} /><input required value={path} onChange={(event) => setPath(event.target.value)} placeholder="Full CSV path inside this project" /><button disabled={!project}>Plan clean copy</button></form><div className="data-pipeline">{stages.map(([number, title, body]) => <article key={number}><span>{number}</span><div><h3>{title}</h3><p>{body}</p></div></article>)}</div></div>;
}

function CreatePanel({ mode, busy, onClose, onSubmit }: { mode: "project" | "agent" | "skill"; busy: boolean; onClose: () => void; onSubmit: (payload: Record<string, unknown>) => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [secondary, setSecondary] = useState("");
  const [path, setPath] = useState("");
  const [repository, setRepository] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (mode === "project") onSubmit({ name, description, ...(path ? { root_path: path } : {}), ...(repository ? { repository_url: repository } : {}) });
    if (mode === "agent") onSubmit({ name, role: secondary || "specialist agent", description, model_policy: "local-auto", capabilities: [] });
    if (mode === "skill") onSubmit({ name, category: secondary || "general", description, risk_level: "low", capabilities: [] });
  };
  return <div className="drawer-backdrop" onMouseDown={onClose}><aside className="create-drawer" onMouseDown={(event) => event.stopPropagation()}><header><div><div className="eyebrow">AEGIS REGISTRY</div><h2>New {mode}</h2></div><button className="icon-button" onClick={onClose}><X size={18} /></button></header><form onSubmit={submit}><label>Name<input required minLength={2} value={name} onChange={(event) => setName(event.target.value)} placeholder={mode === "project" ? "New business project" : mode === "agent" ? "Specialist name" : "Reusable skill"} /></label>{mode !== "project" && <label>{mode === "agent" ? "Role" : "Category"}<input value={secondary} onChange={(event) => setSecondary(event.target.value)} placeholder={mode === "agent" ? "research and analysis" : "creative"} /></label>}<label>Description<textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={4} placeholder="What should Aegis understand about this?" /></label>{mode === "project" && <><label>Registered root path <span>optional</span><input value={path} onChange={(event) => setPath(event.target.value)} placeholder="Uses the protected projects directory by default" /></label><label>GitHub repository <span>optional</span><input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder="https://github.com/owner/repository" /></label></>}<div className="drawer-policy"><ShieldCheck size={16} /><p>{mode === "project" ? "No folder or repository is modified by creating this workspace." : "New definitions start as proposals and require evaluation before expanded permissions."}</p></div><button className="primary-button" disabled={busy || !name.trim()}>{busy ? "Saving…" : `Create ${mode}`}</button></form></aside></div>;
}
