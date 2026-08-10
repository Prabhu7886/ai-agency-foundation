import { FormEvent, KeyboardEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AppWindow,
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
  UserRoundCheck,
  Workflow,
  X,
  Zap,
} from "lucide-react";
import { BrandMark } from "./components/BrandMark";
import {
  bootstrap,
  changePlugin,
  chat,
  createAgent,
  createOpportunity,
  createProject,
  createSolution,
  createSkill,
  decideApproval,
  executeResearch,
  requestResearch,
  requestDataJob,
  speakVoice,
  transcribeVoice,
} from "./api";
import type { Agent, Approval, Bootstrap, Plugin, Project, Skill, Workspace } from "./types";

const workspaceIcons: Record<string, ReactNode> = {
  "executive-home": <CircleGauge size={17} />,
  "ai-workspace": <BrainCircuit size={17} />,
  "agent-fleet": <Network size={17} />,
  "world-pulse": <Globe2 size={17} />,
  "opportunity-engine": <Target size={17} />,
  "solution-factory": <FlaskConical size={17} />,
  "approval-center": <UserRoundCheck size={17} />,
  "security-sentinel": <ShieldCheck size={17} />,
  "voice-lounge": <AudioLines size={17} />,
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

function StatusPill({ children, tone = "neutral" }: { children: ReactNode; tone?: string }) {
  return <span className={`status-pill status-pill--${tone}`}>{children}</span>;
}

type AIChatTurn = {
  id: string;
  request: string;
  answer: string;
  provider: string;
  createdAt: string;
  error?: string;
  compilation?: Awaited<ReturnType<typeof chat>>["compilation"];
};

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
  const [fleetTab, setFleetTab] = useState<"agents" | "skills" | "plugins">("agents");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

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
      return undefined;
    }, decision === "approved" && item.action === "public_web_research" ? "Research completed and report saved" : `Approval ${decision}`);
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
            <div><strong>{data.local_model.model}</strong><small>{data.local_model.available ? "Local model ready" : "Local model offline"}</small></div>
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
            <ExecutiveHome data={data} project={selectedProject} onChat={(message) => mutate(() => chat(selectedProject!.id, message), "Aegis completed the local turn")} />
          )}
          {activeWorkspace === "ai-workspace" && <AIWorkspace project={selectedProject} onRefresh={() => refresh(true)} />}
          {activeWorkspace === "agent-fleet" && (
            <AgentFleet
              agents={data.agents}
              skills={data.skills}
              plugins={data.plugins}
              tab={fleetTab}
              onTab={setFleetTab}
              onCreate={setCreateMode}
              onPlugin={(plugin) => mutate(() => changePlugin(plugin.id, plugin.status !== "enabled"), plugin.status === "enabled" ? "Plugin disabled" : "Plugin approval created")}
            />
          )}
          {activeWorkspace === "world-pulse" && (
            <WorldPulse data={data} project={selectedProject} onResearch={(query) => mutate(() => requestResearch(selectedProject?.id ?? null, query), "Research request sent to Approval Center")} />
          )}
          {activeWorkspace === "opportunity-engine" && <OpportunityEngine data={data} project={selectedProject} onResearch={(query) => mutate(() => requestResearch(selectedProject?.id ?? null, query, "opportunity"), "Opportunity research sent to Approval Center")} onCreate={(payload) => mutate(() => createOpportunity(payload), "Opportunity scored from explicit evidence")} />}
          {activeWorkspace === "solution-factory" && <><SolutionCreateForm onCreate={(payload) => mutate(() => createSolution(payload), "Solution program created at discovery stage")} /><SolutionFactory data={data} onCreate={async () => undefined} /></>}
          {activeWorkspace === "approval-center" && (
            <ApprovalCenter approvals={data.approvals} onDecision={decideAndExecute} />
          )}
          {activeWorkspace === "security-sentinel" && <SecuritySentinel data={data} />}
          {activeWorkspace === "voice-lounge" && <VoiceLounge />}
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
      {toast && <div className="toast"><Check size={16} />{toast}</div>}
    </div>
  );
}

function AIWorkspace({ project, onRefresh }: { project: Project | null; onRefresh: () => Promise<void> }) {
  const [message, setMessage] = useState("");
  const [turns, setTurns] = useState<AIChatTurn[]>([]);
  const [sending, setSending] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const conversationEnd = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    conversationEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, sending]);

  useEffect(() => {
    setTurns([]);
    setMessage("");
  }, [project?.id]);

  const sendMessage = async (request: string, priorTurns: AIChatTurn[]) => {
    if (!project || sending) return;
    setSending(true);
    const history = priorTurns.flatMap((turn) => [
      { role: "user" as const, content: turn.request },
      { role: "assistant" as const, content: turn.answer },
    ]).slice(-12);
    try {
      const result = await chat(project.id, request, history);
      setTurns((current) => [...current, {
        id: crypto.randomUUID(),
        request,
        answer: result.answer,
        provider: result.provider,
        error: result.error,
        compilation: result.compilation,
        createdAt: new Date().toISOString(),
      }]);
      await onRefresh();
    } catch (reason) {
      setTurns((current) => [...current, {
        id: crypto.randomUUID(),
        request,
        answer: "Aegis stopped safely before execution.",
        provider: "none",
        error: reason instanceof Error ? reason.message : "Unknown local error",
        createdAt: new Date().toISOString(),
      }]);
    } finally {
      setSending(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const request = message.trim();
    if (!request || !project || sending) return;
    setMessage("");
    await sendMessage(request, turns);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };

  const copyAnswer = async (turn: AIChatTurn) => {
    await navigator.clipboard.writeText(turn.answer);
    setCopiedId(turn.id);
    window.setTimeout(() => setCopiedId(null), 1500);
  };

  const regenerate = async () => {
    const last = turns.at(-1);
    if (!last || sending) return;
    const prior = turns.slice(0, -1);
    setTurns(prior);
    await sendMessage(last.request, prior);
  };

  return <div className="ai-workspace">
    <header className="ai-workspace__header"><div><div className="eyebrow"><BrainCircuit size={13} /> AEGIS CONVERSATION</div><h2>{project?.name ?? "AI Workspace"}</h2><p>Private local reasoning with your original intent preserved.</p></div><div className="ai-chat-controls"><StatusPill tone="safe">Ollama local</StatusPill><button className="chat-utility" disabled={sending || turns.length === 0} onClick={() => setTurns([])}><Plus size={14} /> New chat</button></div></header>
    <section className="ai-conversation">
      {turns.length === 0 ? <div className="ai-welcome"><div className="ai-welcome__mark"><BrainCircuit size={30} /></div><h3>What are we building?</h3><p>Discuss an idea, analyze a market, make a plan, or prepare a coding task. Aegis keeps the conversation local and shows its execution contract when you need it.</p><div className="ai-starters">{["Turn my idea into a practical plan", "Analyze a business opportunity", "Help me design a secure feature"].map((starter) => <button key={starter} onClick={() => setMessage(starter)}>{starter}<ChevronRight size={13} /></button>)}</div></div> : turns.map((turn) => <article className="ai-turn" key={turn.id}>
        <div className="ai-message ai-message--owner"><div className="ai-avatar ai-avatar--owner">S</div><div><span>You · {new Date(turn.createdAt).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span><p>{turn.request}</p></div></div>
        <div className="ai-message ai-message--aegis"><div className="ai-avatar ai-avatar--aegis"><BrainCircuit size={14} /></div><div className="ai-response"><span>Aegis · {turn.provider}</span><p>{turn.answer}</p>{turn.error && <small>{turn.error}</small>}<div className="ai-message-actions"><button onClick={() => copyAnswer(turn)} title="Copy response">{copiedId === turn.id ? <Check size={13} /> : <Copy size={13} />} {copiedId === turn.id ? "Copied" : "Copy"}</button></div></div></div>
        {turn.compilation && <details className="prompt-contract ai-contract"><summary><Sparkles size={11} /> View rewritten execution contract · {turn.compilation.risk_level} risk</summary><div><label>Objective</label><p>{turn.compilation.objective}</p><label>Compiled prompt</label><pre>{turn.compilation.compiled_prompt}</pre><footer><span>{turn.compilation.compiler_mode}</span><span>{turn.compilation.data_classification}</span></footer></div></details>}
      </article>)}
      {sending && <div className="ai-message ai-message--aegis ai-message--thinking"><div className="ai-avatar ai-avatar--aegis"><BrainCircuit size={14} /></div><div><span>Aegis</span><div className="ai-thinking"><i /><i /><i /> Rewriting your request and thinking locally…</div></div></div>}
      <div ref={conversationEnd} />
    </section>
    <div className="ai-composer-dock">{turns.length > 0 && <button className="regenerate-button" disabled={sending} onClick={regenerate}><RotateCcw size={13} /> Regenerate last response</button>}<form className="ai-composer" onSubmit={submit}><textarea rows={2} value={message} onChange={(event) => setMessage(event.target.value)} onKeyDown={handleKeyDown} placeholder="Message Aegis…" /><footer><div><LockKeyhole size={13} /> Local first · Enter to send · Shift+Enter for a new line</div><button aria-label="Send message" disabled={!message.trim() || !project || sending}><Send size={16} /></button></footer></form><small className="ai-disclaimer">Aegis can make mistakes. Verify important business, security, and financial decisions.</small></div>
  </div>;
}

function ExecutiveHome({ data, project, onChat }: { data: Bootstrap; project: Project | null; onChat: (message: string) => Promise<void> }) {
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
    </div>
  );
}

function Metric({ label, value, icon, accent = false }: { label: string; value: number; icon: ReactNode; accent?: boolean }) {
  return <div className={`metric-card ${accent ? "metric-card--accent" : ""}`}><span>{icon}</span><div><strong>{value}</strong><small>{label}</small></div></div>;
}

function PanelHeader({ icon, title, action }: { icon: ReactNode; title: string; action?: ReactNode }) {
  return <div className="panel-header"><div>{icon}<h3>{title}</h3></div>{action}</div>;
}

function AgentFleet({ agents, skills, plugins, tab, onTab, onCreate, onPlugin }: {
  agents: Agent[]; skills: Skill[]; plugins: Plugin[]; tab: "agents" | "skills" | "plugins";
  onTab: (tab: "agents" | "skills" | "plugins") => void;
  onCreate: (mode: "agent" | "skill") => void;
  onPlugin: (plugin: Plugin) => void;
}) {
  return (
    <div className="single-workspace">
      <div className="workspace-intro"><div><div className="eyebrow">MODULAR INTELLIGENCE</div><h2>Agents do the work.<br /><span>Skills make them stronger.</span></h2><p>Aegis controls versions, permissions, models, evaluations, and shared knowledge.</p></div><Network className="intro-icon" /></div>
      <div className="segmented-tabs">
        {(["agents", "skills", "plugins"] as const).map((item) => <button key={item} className={tab === item ? "active" : ""} onClick={() => onTab(item)}>{item}</button>)}
      </div>
      {tab === "agents" && <CardGrid items={agents} render={(agent) => <AgentCard agent={agent} />} action={<button className="secondary-button" onClick={() => onCreate("agent")}><Plus size={15} /> New agent</button>} />}
      {tab === "skills" && <CardGrid items={skills} render={(skill) => <SkillCard skill={skill} />} action={<button className="secondary-button" onClick={() => onCreate("skill")}><PackagePlus size={15} /> New skill</button>} />}
      {tab === "plugins" && <CardGrid items={plugins} render={(plugin) => <PluginCard plugin={plugin} onChange={() => onPlugin(plugin)} />} />}
    </div>
  );
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

function WorldPulse({ data, project, onResearch }: { data: Bootstrap; project: Project | null; onResearch: (query: string) => Promise<void> }) {
  const [query, setQuery] = useState("");
  const submit = async (event: FormEvent) => { event.preventDefault(); if (!query.trim()) return; const value = query; setQuery(""); await onResearch(value); };
  return <div className="single-workspace"><div className="workspace-intro pulse-intro"><div><div className="eyebrow">GLOBAL IMPACT INTELLIGENCE</div><h2>Signal over noise.<br /><span>Every claim earns its confidence.</span></h2><p>AI, IT, economies, conflicts, trade, gold, silver, politicians, insiders, and institutional holdings.</p></div><Radar className="intro-icon" /></div><form className="research-bar" onSubmit={submit}><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Research a public topic…" /><button disabled={!query.trim()}>Request research</button></form><div className="source-policy"><ShieldCheck size={16} /><span>Public queries only. Web access requires Approval Center authorization and an approved research session.</span></div>{data.world_pulse.length === 0 ? <EmptyState icon={<Globe2 />} title="World Pulse is protected and waiting" body={`No unverified headlines are displayed. Start an approved research task${project ? ` for ${project.name}` : ""}.`} /> : <div className="card-grid">{data.world_pulse.map((item, index) => <article className="entity-card pulse-card" key={index}><div className="pulse-card__meta"><StatusPill tone={String(item.verification_state) === "single_source" ? "neutral" : "safe"}>{String(item.verification_state ?? "unverified").replaceAll("_", " ")}</StatusPill><span>{Math.round(Number(item.confidence ?? 0) * 100)}% source confidence</span></div><h3>{String(item.headline)}</h3><p>{String(item.summary)}</p>{item.source_url && <a href={String(item.source_url)} target="_blank" rel="noreferrer">{String(item.domain ?? "Open source")} <ArrowUpRight size={12} /></a>}</article>)}</div>}</div>;
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

function OpportunityEngine({ data, project, onResearch, onCreate }: {
  data: Bootstrap;
  project: Project | null;
  onResearch: (query: string) => Promise<void>;
  onCreate: (payload: Record<string, unknown>) => Promise<void>;
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
      {reports.length === 0 ? <EmptyState icon={<Radar />} title="No research report yet" body="Submit a public topic, approve it in Approval Center, and Aegis will return here with a source-backed executive report." /> : <div className="research-report-list">{reports.map((item) => <article className="research-report" key={item.id}><header><div><div className="eyebrow">PUBLIC RESEARCH · {new Date(item.created_at).toLocaleString()}</div><h3>{item.report.title}</h3></div><StatusPill tone={item.independent_domains >= 2 ? "safe" : "warning"}>{item.source_count} sources · {item.independent_domains} domains</StatusPill></header><section><h4>Executive Summary</h4><ul>{item.report.executive_summary.map((line) => <li key={line}>{line}</li>)}</ul></section><section><h4>Key findings</h4><div className="report-findings">{item.report.key_findings.map((finding, index) => <article key={`${finding.headline}-${index}`}><div><StatusPill tone={finding.confidence >= .7 ? "safe" : "neutral"}>{Math.round(finding.confidence * 100)}% confidence</StatusPill><span>{finding.source_ids.join(", ")}</span></div><h5>{finding.headline}</h5><p>{finding.evidence}</p><small>{finding.implication}</small></article>)}</div></section><details><summary>Recommendations, questions, caveats, and sources</summary><div className="report-detail-grid"><section><h4>Recommended next steps</h4><ol>{item.report.recommended_next_steps.map((line) => <li key={line}>{line}</li>)}</ol></section><section><h4>Further questions</h4><ul>{item.report.further_questions.map((line) => <li key={line}>{line}</li>)}</ul></section><section><h4>Caveats</h4><ul>{item.report.caveats.map((line) => <li key={line}>{line}</li>)}</ul></section><section><h4>Sources</h4><div className="report-sources">{item.report.sources.map((source) => <a key={source.id} href={source.url} target="_blank" rel="noreferrer"><span>{source.id} · {source.domain}</span>{source.title}<ArrowUpRight size={12} /></a>)}</div></section></div></details></article>)}</div>}
    </section>
    <section className="opportunity-section"><PanelHeader icon={<CircleGauge size={17} />} title="Evidence-backed scorecard" action={<StatusPill>{data.opportunities.length} scored</StatusPill>} /><details className="manual-score"><summary><Plus size={13} /> Score a researched opportunity manually</summary><OpportunityCreateForm onCreate={onCreate} /></details>{data.opportunities.length === 0 ? <EmptyState icon={<Zap />} title="No unsupported promises" body="Score an opportunity only after the research report is reviewed and customer or pricing evidence is attached." /> : <div className="card-grid">{data.opportunities.map((item, index) => <article className="entity-card" key={index}><StatusPill tone="safe">{String(item.score)} / 100</StatusPill><h3>{String(item.title)}</h3><p>{String(item.thesis)}</p><small>{String(item.allocation)}</small></article>)}</div>}</section>
  </div>;
}

function SolutionFactory({ data, onCreate }: { data: Bootstrap; onCreate: (payload: Record<string, unknown>) => Promise<void> }) {
  void onCreate;
  const stages = ["Discover", "Verify", "Design", "Prototype", "Test", "Launch", "Learn"];
  return <div className="single-workspace"><div className="workspace-intro"><div><div className="eyebrow">PROBLEM → PROOF</div><h2>Create solutions<br /><span>people will actually use.</span></h2><p>Start with a real pain, prove demand, build the smallest useful answer, and measure reality.</p></div><FlaskConical className="intro-icon" /></div><div className="factory-flow">{stages.map((stage, index) => <div key={stage}><span>{index + 1}</span><strong>{stage}</strong>{index < stages.length - 1 && <ChevronRight size={16} />}</div>)}</div>{data.solutions.length === 0 ? <EmptyState icon={<BrainCircuit />} title="Factory floor is clear" body="A verified problem will become the first solution program." /> : <div className="card-grid">{data.solutions.map((item, index) => <article className="entity-card" key={index}><StatusPill>{String(item.stage)}</StatusPill><h3>{String(item.title)}</h3><p>{String(item.problem)}</p><small>{String(item.audience)}</small></article>)}</div>}</div>;
}

function ApprovalCenter({ approvals, onDecision }: { approvals: Approval[]; onDecision: (item: Approval, decision: "approved" | "declined") => Promise<void> }) {
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
  return <div className="single-workspace"><div className="workspace-intro compact"><div><div className="eyebrow">HUMAN AUTHORITY</div><h2>Nothing consequential<br /><span>happens in the dark.</span></h2></div><UserRoundCheck className="intro-icon" /></div>{pending.length === 0 ? <EmptyState icon={<Check />} title="Approval queue is clear" body="Aegis will surface evidence, risk, cost, and exact scope before asking." /> : <div className="approval-list">{pending.map((item) => <article key={item.id}><div><StatusPill tone={item.risk_level === "high" || item.risk_level === "critical" ? "danger" : "warning"}>{item.risk_level} risk</StatusPill><span>{timeAgo(item.requested_at)}</span></div><h3>{item.summary}</h3><p>Action: {item.action.replaceAll("_", " ")}</p><pre>{JSON.stringify(item.evidence, null, 2)}</pre><footer><button className="decline-button" disabled={Boolean(runningId)} onClick={() => void decide(item, "declined")}><X size={15} /> Decline</button><button className="approve-button" disabled={Boolean(runningId)} onClick={() => void decide(item, "approved")}>{runningId === item.id ? <Activity size={15} /> : <Check size={15} />} {runningId === item.id && item.action === "public_web_research" ? "Researching…" : item.action === "public_web_research" ? "Approve & run" : "Approve"}</button></footer></article>)}</div>}</div>;
}

function SecuritySentinel({ data }: { data: Bootstrap }) {
  const controls = [
    ["Local API", data.foundation.local_only, String(data.foundation.api_bind)],
    ["SQLCipher", data.foundation.sqlcipher_required, "required"],
    ["Chroma", !data.foundation.chroma_server_enabled, String(data.foundation.vector_store_mode)],
    ["Cloud privacy", data.foundation.cloud_private_data === "blocked", String(data.foundation.cloud_private_data)],
    ["Ollama", data.local_model.available, data.local_model.available ? data.local_model.model : "offline"],
    ["External research", data.foundation.external_research === "approved_public_sessions", String(data.foundation.external_research)],
  ];
  return <div className="single-workspace"><div className="workspace-intro security-intro"><div><div className="eyebrow">CONTINUOUS ASSURANCE</div><h2>Trust evidence.<br /><span>Verify everything.</span></h2><p>The foundation remains authoritative for encryption, local inference, data handling, approvals, and network boundaries.</p></div><ShieldCheck className="intro-icon" /></div><div className="security-grid">{controls.map(([name, passed, detail]) => <article key={String(name)} className={passed ? "passed" : "guarded"}><span>{passed ? <Check /> : <LockKeyhole />}</span><div><h3>{String(name)}</h3><p>{String(detail)}</p></div></article>)}</div><div className="panel policy-panel"><PanelHeader icon={<FileCode2 size={17} />} title="Inherited foundation" action={<StatusPill tone="safe">Enforced</StatusPill>} /><p>Every Aegis workspace, agent, skill, and plugin passes through the same SQLCipher, loopback, offline-mode, secret-redaction, and approval controls.</p></div></div>;
}

function VoiceLounge() {
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
