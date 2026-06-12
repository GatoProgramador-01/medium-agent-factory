"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, type AgentLog, type Post } from "@/lib/api";

const STATUSES = ["", "draft", "revised", "approved", "published", "draft_submitted"];

const STATUS_COLOR: Record<string, string> = {
  approved:        "text-[var(--accent)]",
  published:       "text-[var(--blue)]",
  draft_submitted: "text-[var(--blue)]",
  revised:         "text-[var(--yellow)]",
  draft:           "text-[var(--muted)]",
  failed:          "text-[var(--red)]",
};

// ── Publisher terminal ────────────────────────────────────────────────────────

function PublisherTerminal({
  runId,
  onClose,
}: {
  runId: string;
  onClose: () => void;
}) {
  const [logs, setLogs]     = useState<AgentLog[]>([]);
  const [done, setDone]     = useState(false);
  const [error, setError]   = useState<string | null>(null);
  const logEndRef           = useRef<HTMLDivElement>(null);
  const pollRef             = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const poll = async () => {
      try {
        const all = await api.getLogs(runId);
        const pub = all.filter((l) => l.step === "publisher");
        setLogs(pub);
        const last = pub[pub.length - 1];
        if (last?.level === "success" && last.message.startsWith("Done")) {
          clearInterval(pollRef.current!);
          setDone(true);
        }
        if (last?.level === "error") {
          clearInterval(pollRef.current!);
          setError(last.message);
          setDone(true);
        }
      } catch { /* ignore */ }
    };
    poll();
    pollRef.current = setInterval(poll, 1500);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [runId]);

  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [logs]);

  const LEVEL: Record<string, string> = {
    info:    "text-[var(--muted)]",
    success: "text-[var(--accent)]",
    warning: "text-[var(--yellow)]",
    error:   "text-[var(--red)]",
  };

  return (
    <div className="term-box mt-3">
      <div className="term-box-header">
        <span className={done ? "text-[var(--accent)]" : "text-[var(--yellow)] animate-pulse"}>●</span>
        <span>publisher · {runId.slice(0, 8)}…</span>
        <span className="ml-auto text-[10px]">{done ? "done" : "running…"}</span>
        {done && (
          <button onClick={onClose} className="ml-3 text-[var(--muted)] hover:text-[var(--text)] transition-colors">
            [close]
          </button>
        )}
      </div>
      <div className="p-3 font-mono text-xs space-y-0.5 max-h-64 overflow-y-auto">
        {logs.length === 0 && !error && (
          <p className="text-[var(--muted)] animate-pulse">initializing…</p>
        )}
        {logs.map((l, i) => (
          <div key={i} className="flex gap-2">
            <span className="text-[var(--muted)] w-20 shrink-0 tabular-nums">
              {new Date(l.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </span>
            <span className={LEVEL[l.level] ?? "text-[var(--muted)]"}>{l.message}</span>
          </div>
        ))}
        <div ref={logEndRef} />
      </div>
    </div>
  );
}

// ── Score bar ─────────────────────────────────────────────────────────────────

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const fill = pct >= 75 ? "bg-[var(--accent)]" : pct >= 50 ? "bg-[var(--yellow)]" : "bg-[var(--red)]";
  const text = pct >= 75 ? "text-[var(--accent)]" : pct >= 50 ? "text-[var(--yellow)]" : "text-[var(--red)]";
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className={`tabular-nums w-7 ${text}`}>{pct}</span>
      <div className="flex-1 h-1 bg-[var(--border)] rounded-full overflow-hidden">
        <div className={`h-full ${fill} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// ── Post card ─────────────────────────────────────────────────────────────────

function PostCard({ post, onPublished }: { post: Post; onPublished: () => void }) {
  const [expanded, setExpanded]       = useState(false);
  const [publishing, setPublishing]   = useState(false);
  const [publishLive, setPublishLive] = useState(false);
  const [showTerminal, setShowTerminal] = useState(false);
  const statusColor = STATUS_COLOR[post.status] ?? "text-[var(--muted)]";
  const canPublish  = post.status === "approved";

  async function handlePublish() {
    setPublishing(true);
    setShowTerminal(true);
    try {
      await api.publishPost(post.run_id, publishLive);
    } catch (e) {
      console.error(e);
    }
  }

  return (
    <div className="border-b border-[var(--border)] last:border-0 py-3 px-4 hover:bg-[var(--surface2)] transition-colors" data-testid="post-card">
      {/* Header row */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-xs shrink-0 ${statusColor}`}>[{post.status}]</span>
            <p className="text-sm font-medium truncate text-[var(--text)]">{post.title}</p>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-[var(--muted)]">
            <span>{new Date(post.created_at).toISOString().slice(0, 10)}</span>
            <span>{post.revision_count} rev</span>
            {post.tags.map((t) => <span key={t} className="text-[var(--border2)]">#{t}</span>)}
          </div>
        </div>
        <div className="shrink-0 w-32">
          {post.quality_report
            ? <ScoreBar score={post.quality_report.score} />
            : <span className="text-[10px] text-[var(--muted)]">no score</span>
          }
        </div>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="mt-3 space-y-2">
          {post.quality_report && (
            <div className="text-xs text-[var(--muted)] flex gap-4">
              <span>read_ratio: <span className="text-[var(--accent)]">{Math.round(post.quality_report.read_ratio_prediction * 100)}%</span></span>
              {post.quality_report.strengths.length > 0 && (
                <span>strengths: <span className="text-[var(--text)]">{post.quality_report.strengths.slice(0, 2).join(", ")}</span></span>
              )}
            </div>
          )}
          <pre className="text-[11px] bg-[var(--bg)] p-3 overflow-auto max-h-64 text-[var(--muted)] leading-relaxed whitespace-pre-wrap">
            {post.content.slice(0, 800)}{post.content.length > 800 ? "…" : ""}
          </pre>
        </div>
      )}

      {/* Publish panel (approved posts only) */}
      {canPublish && !showTerminal && (
        <div className="mt-3 flex items-center gap-3 flex-wrap">
          <label className="flex items-center gap-2 text-[10px] text-[var(--muted)] cursor-pointer select-none">
            <input
              type="checkbox"
              checked={publishLive}
              onChange={(e) => setPublishLive(e.target.checked)}
              className="accent-[var(--accent)]"
            />
            --publish-live
          </label>
          <button
            onClick={handlePublish}
            disabled={publishing}
            className="term-btn term-btn-solid text-[10px] px-3 py-1 tracking-widest"
          >
            ❯ publish_to_medium
          </button>
          {post.medium_url && (
            <a href={post.medium_url} target="_blank" rel="noopener noreferrer"
              className="text-[10px] text-[var(--blue)] hover:underline">
              [open_medium ↗]
            </a>
          )}
        </div>
      )}

      {/* Live publisher terminal */}
      {showTerminal && (
        <PublisherTerminal
          runId={post.run_id}
          onClose={() => { setShowTerminal(false); setPublishing(false); onPublished(); }}
        />
      )}

      {/* Footer controls */}
      <div className="flex gap-4 mt-2">
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-[10px] text-[var(--muted)] hover:text-[var(--accent)] transition-colors"
        >
          [{expanded ? "collapse" : "expand"}]
        </button>
        {post.medium_url && !canPublish && (
          <a href={post.medium_url} target="_blank" rel="noopener noreferrer"
            className="text-[10px] text-[var(--muted)] hover:text-[var(--blue)] transition-colors">
            [open_medium ↗]
          </a>
        )}
      </div>
    </div>
  );
}

// ── Auth helper modal ─────────────────────────────────────────────────────────

type AuthTab = "cdp" | "cookie";

function AuthModal({
  onClose,
  onSaved,
  cdpOk,
}: {
  onClose: () => void;
  onSaved: () => void;
  cdpOk: boolean | null;
}) {
  const [tab, setTab]         = useState<AuthTab>(cdpOk ? "cookie" : "cdp");
  const [sid, setSid]         = useState("");
  const [message, setMessage] = useState("");
  const [error, setError]     = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone]       = useState(false);

  async function handleSave() {
    setLoading(true);
    setError("");
    try {
      const r = await api.setMediumSession(sid.trim());
      setMessage(r.message);
      setDone(true);
      onSaved();
    } catch (e) {
      setError(String(e).replace("Error: API 422: ", "").replace("Error: API 500: ", ""));
    } finally {
      setLoading(false);
    }
  }

  const chromeCmd = `"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%TEMP%\\chrome-debug"`;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="term-box w-full max-w-lg">
        <div className="term-box-header">
          <span className="text-[var(--accent)]">$</span>
          <span>medium · connect session</span>
          <button onClick={onClose} className="ml-auto text-[var(--muted)] hover:text-[var(--text)]">[×]</button>
        </div>

        {/* Tab bar */}
        <div className="flex border-b border-[var(--border)]">
          {(["cdp", "cookie"] as AuthTab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-[10px] tracking-widest transition-colors ${
                tab === t
                  ? "border-b border-[var(--accent)] text-[var(--accent)]"
                  : "text-[var(--muted)] hover:text-[var(--text)]"
              }`}
            >
              {t === "cdp" ? (
                <span className="flex items-center gap-1.5">
                  <span className={cdpOk ? "text-[var(--accent)]" : "text-[var(--red)]"}>●</span>
                  CDP (recommended)
                </span>
              ) : "sid cookie (fallback)"}
            </button>
          ))}
        </div>

        <div className="p-5 space-y-4 text-xs font-mono">

          {tab === "cdp" && (
            <>
              {cdpOk ? (
                <div className="space-y-2">
                  <p className="text-[var(--accent)]">✓ Chrome is connected via CDP</p>
                  <p className="text-[var(--muted)]">
                    When you publish, a new tab will open in your Chrome browser
                    and Medium will be controlled through it — no Cloudflare blocking.
                  </p>
                  <p className="text-[var(--muted)]">
                    Make sure you are logged into <span className="text-[var(--blue)]">medium.com</span> in that browser.
                  </p>
                  <button onClick={onClose} className="term-btn w-full py-2 tracking-widest mt-2">
                    [close]
                  </button>
                </div>
              ) : (
                <div className="space-y-3 text-[var(--muted)] leading-relaxed">
                  <p className="text-[var(--text)]">Start Chrome with remote debugging enabled:</p>
                  <p>1. <span className="text-[var(--yellow)]">Close all Chrome windows</span> first</p>
                  <p>2. Run this command in PowerShell or CMD:</p>
                  <pre className="bg-[var(--bg)] border border-[var(--border)] p-3 text-[10px] leading-relaxed overflow-auto whitespace-pre-wrap break-all text-[var(--accent)]">
                    {chromeCmd}
                  </pre>
                  <p>3. Log in to <span className="text-[var(--blue)]">medium.com</span> in that Chrome window</p>
                  <p>4. Come back here — the <span className="text-[var(--accent)]">CDP</span> dot will turn green</p>
                  <div className="border-t border-[var(--border)] pt-3">
                    <p className="text-[10px]">Verify it&apos;s working: open <span className="text-[var(--blue)]">http://localhost:9222/json/version</span> — you should see JSON.</p>
                  </div>
                  <button onClick={onClose} className="term-btn w-full py-2 tracking-widest">
                    [close — I&apos;ll start Chrome]
                  </button>
                </div>
              )}
            </>
          )}

          {tab === "cookie" && (
            <>
              <div className="space-y-1 text-[var(--muted)] leading-relaxed">
                <p className="text-[var(--text)]">How to find your <span className="text-[var(--accent)]">sid</span> cookie:</p>
                <p>1. Open <span className="text-[var(--blue)]">medium.com</span> in Chrome/Firefox while logged in</p>
                <p>2. Press <span className="text-[var(--yellow)]">F12</span> → <span className="text-[var(--yellow)]">Application</span> (Chrome) or <span className="text-[var(--yellow)]">Storage</span> (Firefox)</p>
                <p>3. <span className="text-[var(--yellow)]">Cookies</span> → <span className="text-[var(--yellow)]">https://medium.com</span></p>
                <p>4. Find the row named <span className="text-[var(--accent)]">sid</span> → copy the <span className="text-[var(--accent)]">Value</span></p>
              </div>

              <div className="border-t border-[var(--border)]" />

              <div>
                <label className="text-[var(--muted)] mb-1 block">paste sid value:</label>
                <div className="flex items-center gap-2 border border-[var(--border)] bg-[var(--bg)] px-3 py-2 focus-within:border-[var(--accent)] transition-colors">
                  <span className="text-[var(--accent)]">❯</span>
                  <input
                    value={sid}
                    onChange={(e) => setSid(e.target.value)}
                    placeholder="2:AbCdEf…"
                    type="password"
                    className="flex-1 bg-transparent focus:outline-none text-[var(--text)] placeholder:text-[var(--muted)] font-mono text-xs"
                  />
                </div>
              </div>

              {error && <p className="text-[var(--red)] leading-relaxed">{error}</p>}

              {done ? (
                <>
                  <p className="text-[var(--accent)]">✓ {message}</p>
                  <button onClick={onClose} className="term-btn w-full py-2 tracking-widest">
                    [close]
                  </button>
                </>
              ) : (
                <button
                  onClick={handleSave}
                  disabled={loading || !sid.trim()}
                  className="term-btn term-btn-solid w-full py-2 tracking-widest disabled:opacity-40"
                >
                  {loading ? "verifying session…" : "❯ save_session"}
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PostsPage() {
  const [posts, setPosts]         = useState<Post[]>([]);
  const [filter, setFilter]       = useState("");
  const [loading, setLoading]     = useState(true);
  const [showAuth, setShowAuth]   = useState(false);
  const [sessionOk, setSessionOk] = useState<boolean | null>(null);
  const [cdpOk, setCdpOk]         = useState<boolean | null>(null);

  async function load() {
    setLoading(true);
    api.listPosts(filter || undefined)
      .then(setPosts)
      .catch(console.error)
      .finally(() => setLoading(false));
  }

  async function checkSession() {
    try {
      const s = await api.checkMediumSession();
      setSessionOk(s.has_session && s.valid);
    } catch {
      setSessionOk(false);
    }
  }

  async function checkCdp() {
    try {
      const c = await api.checkCdpStatus();
      setCdpOk(c.connected);
    } catch {
      setCdpOk(false);
    }
  }

  useEffect(() => { load(); }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { checkSession(); checkCdp(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-5">
      {showAuth && (
        <AuthModal
          onClose={() => setShowAuth(false)}
          onSaved={() => { setSessionOk(true); setShowAuth(false); }}
          cdpOk={cdpOk}
        />
      )}

      <div>
        <p className="text-[var(--muted)] text-xs mb-1">user@factory:~/factory$</p>
        <h1 className="text-[var(--accent)] text-xl font-bold" data-testid="page-heading">Posts</h1>
        <p className="text-[var(--muted)] text-xs mt-1">ls -la ./posts --filter=status</p>
      </div>

      {/* Filter + auth */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[var(--muted)] text-xs">--status:</span>
        {STATUSES.map((s) => (
          <button
            key={s}
            data-testid={`filter-${s || "all"}`}
            onClick={() => setFilter(s)}
            className={`text-[10px] px-2.5 py-1 border transition-colors tracking-wider ${
              filter === s
                ? "border-[var(--accent)] text-[var(--accent)] bg-[var(--accent-dim)]"
                : "border-[var(--border)] text-[var(--muted)] hover:border-[var(--border2)] hover:text-[var(--text)]"
            }`}
          >
            {s || "all"}
          </button>
        ))}
        <button
          onClick={() => setShowAuth(true)}
          className="ml-auto flex items-center gap-1.5 text-[10px] text-[var(--muted)] hover:text-[var(--accent)] transition-colors border border-transparent hover:border-[var(--border)] px-2 py-1"
        >
          {/* CDP dot */}
          <span
            title={cdpOk ? "Chrome CDP connected" : "Chrome CDP not connected"}
            className={
              cdpOk === null ? "text-[var(--muted)]" :
              cdpOk ? "text-[var(--accent)]" : "text-[var(--border2)]"
            }
          >●</span>
          {/* session dot */}
          <span
            title={sessionOk ? "Cookie session valid" : "No cookie session"}
            className={
              sessionOk === null ? "text-[var(--muted)]" :
              sessionOk ? "text-[var(--blue)]" : "text-[var(--border2)]"
            }
          >●</span>
          <span>[medium]</span>
        </button>
      </div>

      {/* List */}
      <div className="term-box">
        <div className="term-box-header">
          <span>output</span>
          {!loading && <span className="ml-auto text-[var(--accent)]">{posts.length} results</span>}
        </div>

        {loading ? (
          <div className="p-4 space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex gap-4">
                <div className="skeleton h-3 w-16" /><div className="skeleton h-3 flex-1" /><div className="skeleton h-3 w-24" />
              </div>
            ))}
          </div>
        ) : posts.length === 0 ? (
          <div className="p-8 text-center space-y-4" data-testid="empty-state">
            <p className="text-[var(--muted)] text-xs">no posts found</p>
            <p className="text-[var(--border2)] text-[10px]">
              {filter ? `no posts with status "${filter}"` : "run the pipeline to generate your first post"}
            </p>
            <Link href="/pipeline" data-testid="empty-cta"
              className="inline-block term-btn term-btn-solid px-6 py-2 text-xs tracking-widest">
              ❯ run_pipeline
            </Link>
          </div>
        ) : (
          <div>
            {posts.map((p) => <PostCard key={p.run_id} post={p} onPublished={load} />)}
          </div>
        )}
      </div>
    </div>
  );
}
