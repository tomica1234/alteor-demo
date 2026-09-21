import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, setApiUser } from './api'
import type {
  AnswerPayload,
  Approval,
  AuditEvent,
  CaseDocument,
  CaseMember,
  CaseOverview,
  Citation,
  DecisionChatMessage,
  Deadline,
  LegalCase,
  Message,
  DraftVersion,
  FindingResolution,
  TaskType,
  User,
} from './workspace-types'
import './Workspace.css'

type WorkspaceView = 'dashboard' | 'shared' | 'overview' | 'documents' | 'assistant' | 'calendar' | 'chat' | 'approvals' | 'audit'
type CaseView = Exclude<WorkspaceView, 'dashboard' | 'shared'>

type WorkspaceIconName = 'home' | 'case' | 'spark' | 'documents' | 'calendar' | 'chat' | 'check' | 'history'

const caseViews: Array<{ id: CaseView; label: string; icon: WorkspaceIconName }> = [
  { id: 'overview', label: '案件概要', icon: 'case' },
  { id: 'documents', label: '入力資料', icon: 'documents' },
  { id: 'assistant', label: 'AI作成ファイル', icon: 'spark' },
  { id: 'calendar', label: '期限・カレンダー', icon: 'calendar' },
  { id: 'chat', label: '案件チャット', icon: 'chat' },
  { id: 'approvals', label: '確認・承認', icon: 'check' },
  { id: 'audit', label: '操作履歴', icon: 'history' },
]

const taskOptions: Array<{ id: TaskType; title: string; description: string; prompt: string; icon: string }> = [
  {
    id: 'draft',
    title: '書類案を作成',
    description: '登録資料をもとに書類案を作成',
    prompt: '登録資料をもとに書類案を作成してください。事実と推測を分け、確認が必要な箇所を明示してください。',
    icon: '文',
  },
  {
    id: 'consistency_check',
    title: '整合性を確認',
    description: '氏名・日付・金額・引用を資料と照合',
    prompt: '登録資料と書類案を照合し、誤字脱字、氏名、日付、金額、引用箇所、証拠番号の不一致候補を示してください。',
    icon: '照',
  },
]

const stages = ['依頼内容を確認', '資料を確認', '書類案を作成', '確認事項を整理']

export default function Workspace() {
  const [view, setView] = useState<WorkspaceView>('dashboard')
  const [menuOpen, setMenuOpen] = useState(false)
  const [showCreateCase, setShowCreateCase] = useState(false)
  const [users, setUsers] = useState<User[]>([])
  const [currentUserId, setCurrentUserId] = useState(() => window.localStorage.getItem('alteor-user-id') || 'user-admin')
  const [cases, setCases] = useState<LegalCase[]>([])
  const [currentCaseId, setCurrentCaseId] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [authReady, setAuthReady] = useState(false)
  const [authRequired, setAuthRequired] = useState(false)
  const [authenticated, setAuthenticated] = useState(true)
  const [authError, setAuthError] = useState('')
  const currentCase = cases.find((item) => item.id === currentCaseId) ?? null
  const currentUser = users.find((item) => item.id === currentUserId) ?? null

  const loadShell = useCallback(async (preferredCaseId?: string) => {
    setLoading(true)
    setError('')
    try {
      const [nextUsers, nextCases] = await Promise.all([api.users(), api.cases()])
      setUsers(nextUsers)
      setCases(nextCases)
      setCurrentCaseId((existing) => {
        const requested = preferredCaseId || existing
        return nextCases.some((item) => item.id === requested) ? requested : nextCases[0]?.id || ''
      })
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    setApiUser(currentUserId)
    if (!authReady || !authenticated) return undefined
    const timer = window.setTimeout(() => void loadShell(), 0)
    return () => window.clearTimeout(timer)
  }, [currentUserId, authReady, authenticated, loadShell])

  useEffect(() => {
    let active = true
    const timer = window.setTimeout(() => {
      void api.authStatus()
        .then((status) => {
          if (!active) return
          setAuthRequired(status.required)
          setAuthenticated(status.authenticated)
        })
        .catch((caught) => {
          if (active) setError(errorMessage(caught))
        })
        .finally(() => {
          if (active) setAuthReady(true)
        })
    }, 0)
    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [])

  function selectView(nextView: WorkspaceView) {
    setView(nextView)
    setMenuOpen(false)
  }

  function openCase(caseId: string, destination: CaseView = 'overview') {
    setCurrentCaseId(caseId)
    setView(destination)
    setMenuOpen(false)
  }

  function handleUserChange(userId: string) {
    setApiUser(userId)
    setCurrentUserId(userId)
  }

  async function handleLogin(password: string) {
    setAuthError('')
    try {
      await api.login(password)
      setAuthenticated(true)
    } catch (caught) {
      setAuthError(errorMessage(caught))
    }
  }

  if (!authReady) {
    return (
      <main className="wk-boot">
        <span className="wk-brand-glyph">A</span>
        <strong>Alteorを起動しています</strong>
        <i />
      </main>
    )
  }

  if (authRequired && !authenticated) return <AccessGate error={authError} onSubmit={handleLogin} />

  if (loading && !currentCase) {
    return (
      <main className="wk-boot">
        <span className="wk-brand-glyph">A</span>
        <strong>案件情報を読み込んでいます</strong>
        <i />
      </main>
    )
  }

  return (
    <div className="wk-shell">
      <aside className={`wk-sidebar ${menuOpen ? 'open' : ''}`}>
        <button className="wk-brand" onClick={() => selectView('dashboard')} type="button">
          <span>A</span><div><strong>Alteor</strong><small>案件管理</small></div>
        </button>
        <button aria-current={view === 'dashboard' ? 'page' : undefined} className="wk-profile-card" onClick={() => selectView('dashboard')} type="button">
          <span>{currentUser?.initials || '?'}</span>
          <div><strong>{currentUser?.display_name || '利用者'}さん</strong><small>個人ダッシュボード</small></div>
          <WorkspaceIcon name="home" />
        </button>
        <nav aria-label="ワークスペース" className="wk-tree">
          <section className="wk-tree-section">
            <p className="wk-tree-heading">共通領域</p>
            <button aria-current={view === 'shared' ? 'page' : undefined} className="wk-tree-root" onClick={() => selectView('shared')} type="button">
              <i><WorkspaceIcon name="documents" /></i><span>共通資料・条件</span>
            </button>
          </section>
          <section className="wk-tree-section">
            <div className="wk-tree-heading-row"><p className="wk-tree-heading">案件</p><button aria-label="案件を追加" onClick={() => setShowCreateCase(true)} type="button">＋</button></div>
            <div className="wk-tree-cases">
              {cases.map((item) => {
                const expanded = currentCaseId === item.id && view !== 'dashboard' && view !== 'shared'
                return (
                  <div className="wk-tree-case" key={item.id}>
                    <button aria-current={expanded && view === 'overview' ? 'page' : undefined} className={`wk-tree-case-button ${expanded ? 'expanded' : ''}`} onClick={() => openCase(item.id, 'overview')} type="button">
                      <span aria-hidden="true" className="wk-tree-expander">{expanded ? '⌄' : '›'}</span>
                      <WorkspaceIcon name="case" />
                      <span className="wk-tree-case-label"><strong>{item.name}</strong><small>{item.client_name}</small></span>
                      {item.pending_approval_count > 0 && <b>{item.pending_approval_count}</b>}
                    </button>
                    {expanded && <div className="wk-tree-children">
                      {caseViews.slice(1).map((subitem) => (
                        <button aria-current={view === subitem.id ? 'page' : undefined} data-testid={`workspace-nav-${subitem.id}`} key={subitem.id} onClick={() => selectView(subitem.id)} type="button">
                          <i><WorkspaceIcon name={subitem.icon} /></i><span>{subitem.label}</span>
                          {subitem.id === 'calendar' && Boolean(item.deadline_count) && <b>{item.deadline_count}</b>}
                        </button>
                      ))}
                    </div>}
                  </div>
                )
              })}
              {!cases.length && <p className="wk-tree-empty">案件はありません</p>}
            </div>
          </section>
        </nav>
        <button className="wk-new-case-button" onClick={() => setShowCreateCase(true)} type="button">＋ 案件を追加</button>
      </aside>

      <section className="wk-main">
        <header className="wk-topbar">
          <button aria-label={menuOpen ? 'メニューを閉じる' : 'メニューを開く'} className="wk-menu" onClick={() => setMenuOpen((open) => !open)} type="button"><span /><span /><span /></button>
          <div className="wk-topbar-title">
            <small>{view === 'dashboard' ? '個人ダッシュボード' : view === 'shared' ? '共通領域' : caseViews.find((item) => item.id === view)?.label}</small>
            <strong>{view === 'dashboard' ? `${currentUser?.display_name || '利用者'}さんの担当案件` : view === 'shared' ? '共通資料・条件' : currentCase?.name || '案件を選択'}</strong>
          </div>
          {view !== 'dashboard' && view !== 'shared' && currentCase && <label className="wk-case-select">
            <span>案件</span>
            <select onChange={(event) => openCase(event.target.value, view)} value={currentCaseId}>
              {cases.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>}
          <label className="wk-user-select">
            <span className="wk-user-avatar">{currentUser?.initials || '?'}</span>
            <select aria-label="利用者を切り替え" onChange={(event) => handleUserChange(event.target.value)} value={currentUserId}>
              {users.map((user) => <option key={user.id} value={user.id}>{user.display_name}（{roleLabel(user.role)}）</option>)}
            </select>
          </label>
        </header>

        {error && <div className="wk-global-error" role="alert"><strong>システムに接続できません</strong><span>{error}</span><button onClick={() => void loadShell()} type="button">再試行</button></div>}

        <div className="wk-content">
          {view === 'dashboard' && <DashboardView cases={cases} currentUser={currentUser} onCreateCase={() => setShowCreateCase(true)} onOpenCase={openCase} />}
          {view === 'shared' && <SharedResourcesView />}
          {currentCase && view === 'overview' && <OverviewView caseId={currentCase.id} currentUser={currentUser} onChanged={() => void loadShell(currentCase.id)} onNavigate={selectView} />}
          {currentCase && view === 'documents' && <DocumentsView caseId={currentCase.id} onChanged={() => void loadShell(currentCase.id)} onNavigate={selectView} />}
          {currentCase && view === 'assistant' && <AssistantView caseId={currentCase.id} onChanged={() => void loadShell(currentCase.id)} onNavigate={selectView} />}
          {currentCase && view === 'calendar' && <CalendarView caseId={currentCase.id} currentUser={currentUser} onChanged={() => void loadShell(currentCase.id)} />}
          {currentCase && view === 'chat' && <CaseChatView caseId={currentCase.id} currentUser={currentUser} />}
          {currentCase && view === 'approvals' && <ApprovalsView caseId={currentCase.id} currentUser={currentUser} onChanged={() => void loadShell(currentCase.id)} />}
          {currentCase && view === 'audit' && <AuditView caseId={currentCase.id} />}
        </div>
      </section>
      {menuOpen && <button aria-label="メニューを閉じる" className="wk-scrim" onClick={() => setMenuOpen(false)} type="button" />}
      {showCreateCase && (
        <div className="wk-modal-layer" role="presentation">
          <button aria-label="案件作成を閉じる" className="wk-modal-scrim" onClick={() => setShowCreateCase(false)} type="button" />
          <section aria-labelledby="wk-new-case-title" aria-modal="true" className="wk-modal" role="dialog">
            <header><div><h2 id="wk-new-case-title">案件を作成</h2></div><button aria-label="閉じる" onClick={() => setShowCreateCase(false)} type="button">×</button></header>
            <p>案件名と依頼人・対象者を登録します。</p>
            <NewCaseForm onCreated={(caseId) => { setShowCreateCase(false); setMenuOpen(false); openCase(caseId); void loadShell(caseId) }} />
          </section>
        </div>
      )}
    </div>
  )
}

function AccessGate({ error, onSubmit }: { error: string; onSubmit: (password: string) => Promise<void> }) {
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!password || submitting) return
    setSubmitting(true)
    await onSubmit(password)
    setSubmitting(false)
  }

  return (
    <main className="wk-access">
      <section className="wk-access-card" aria-labelledby="wk-access-title">
        <span className="wk-brand-glyph">A</span>
        <p className="wk-eyebrow">ALTEOR / 案件管理</p>
        <h1 id="wk-access-title">パスワードを入力してください</h1>
        <p>この案件管理画面を開くには、共有パスワードが必要です。</p>
        <form onSubmit={submit}>
          <label htmlFor="wk-access-password">パスワード</label>
          <input autoComplete="current-password" id="wk-access-password" onChange={(event) => setPassword(event.target.value)} type="password" value={password} />
          {error && <span className="wk-access-error" role="alert">{error}</span>}
          <button className="wk-primary" disabled={!password || submitting} type="submit">{submitting ? '確認しています…' : 'ログイン'}</button>
        </form>
      </section>
    </main>
  )
}

function SharedResourcesView() {
  const [editing, setEditing] = useState(false)
  const [saved, setSaved] = useState(false)
  const [condition, setCondition] = useState('事実と推測を分け、確認が必要な箇所を明示する')
  const [draftCondition, setDraftCondition] = useState(condition)

  function saveCondition() {
    setCondition(draftCondition)
    setEditing(false)
    setSaved(true)
  }

  return (
    <div className="wk-view wk-shared-view">
      <div className="wk-view-heading compact">
        <div><p className="wk-eyebrow">共通領域</p><h1>共通資料・条件</h1><p>すべての案件で使う書式、確認項目、書類作成時の条件を管理します。</p></div>
      </div>

      <div className="wk-shared-grid">
        <section className="wk-section wk-shared-card">
          <header><div><p className="wk-eyebrow">共通資料</p><h2>すべての案件で参照する資料</h2></div><span className="wk-section-count">3件</span></header>
          <ul className="wk-resource-list">
            <li><WorkspaceIcon name="documents" /><span><strong>所内提出書式.docx</strong><small>提出用の基本書式・更新 2026年7月29日</small></span><b>DOCX</b></li>
            <li><WorkspaceIcon name="documents" /><span><strong>事実確認チェックリスト.xlsx</strong><small>提出前に確認する項目・更新 2026年7月28日</small></span><b>XLSX</b></li>
            <li><WorkspaceIcon name="documents" /><span><strong>案件共通の表記ルール.txt</strong><small>氏名、日付、金額の表記方法・更新 2026年7月25日</small></span><b>TXT</b></li>
          </ul>
          <p className="wk-section-note">共通資料は、案件ごとの入力資料と分けて管理されます。</p>
        </section>

        <section className="wk-section wk-shared-card">
          <header><div><p className="wk-eyebrow">作成条件</p><h2>書類作成時の共通条件</h2></div>{!editing && <button className="wk-secondary" onClick={() => { setDraftCondition(condition); setSaved(false); setEditing(true) }} type="button">編集</button>}</header>
          {editing ? <div className="wk-shared-editor">
            <label htmlFor="wk-shared-condition">文章の扱い</label>
            <textarea id="wk-shared-condition" onChange={(event) => setDraftCondition(event.target.value)} value={draftCondition} />
            <div><button className="wk-secondary" onClick={() => setEditing(false)} type="button">キャンセル</button><button className="wk-primary" onClick={saveCondition} type="button">保存</button></div>
          </div> : <dl className="wk-shared-settings">
            <div><dt>書類の用途</dt><dd>所内確認を初期値にする</dd></div>
            <div><dt>確認する項目</dt><dd>氏名・日付・金額・引用・証拠番号</dd></div>
            <div><dt>文章の扱い</dt><dd>{condition}</dd></div>
          </dl>}
          {saved && <p className="wk-save-note" role="status">共通条件を保存しました。</p>}
          <p className="wk-section-note">案件画面では、ここで設定した条件を引き継いだうえで、案件ごとの条件を追加できます。</p>
        </section>
      </div>
    </div>
  )
}

function DashboardView({ cases, currentUser, onOpenCase, onCreateCase }: {
  cases: LegalCase[]
  currentUser: User | null
  onOpenCase: (caseId: string, destination?: CaseView) => void
  onCreateCase: () => void
}) {
  const totalDeadlines = cases.reduce((total, item) => total + (item.deadline_count || 0), 0)
  const today = new Date()
  const todayKey = localDateKey(today)
  const nearLimitKey = localDateKey(new Date(today.getFullYear(), today.getMonth(), today.getDate() + 7))
  const nearDeadlineCases = cases.filter((item) => Boolean(item.next_deadline_at && item.next_deadline_at >= todayKey && item.next_deadline_at <= nearLimitKey)).length
  return (
    <div className="wk-view wk-dashboard">
      <div className="wk-view-heading">
        <div><p className="wk-eyebrow">ダッシュボード</p><h1>{currentUser?.display_name || '利用者'}さんの担当案件</h1><p>担当案件と承認待ちの作成結果を確認できます。</p></div>
        <button className="wk-primary" onClick={onCreateCase} type="button">＋ 新しい案件</button>
      </div>

      <div className="wk-dashboard-stats">
        <article><span className="blue"><WorkspaceIcon name="case" /></span><div><small>担当案件</small><strong>{cases.length}</strong><p>担当中の案件</p></div></article>
        <article><span className="violet"><WorkspaceIcon name="calendar" /></span><div><small>期限</small><strong>{totalDeadlines}</strong><p>未完了の締め切り</p></div></article>
        <article><span className="orange"><WorkspaceIcon name="calendar" /></span><div><small>期限が近い案件</small><strong>{nearDeadlineCases}</strong><p>7日以内に期限が来る案件</p></div></article>
      </div>

      <section className="wk-case-section">
        <header><div><p className="wk-eyebrow">案件一覧</p><h2>担当案件</h2></div><span>{cases.length}件</span></header>
        {cases.length ? <div className="wk-case-grid">
          {cases.map((item) => (
            <article key={item.id}>
              <button className="wk-case-card-body" onClick={() => onOpenCase(item.id)} type="button">
                <header><span>{caseStatusLabel(item.status)}</span><small>{item.id}</small></header>
                <h3>{item.name}</h3>
                <strong>{item.client_name}</strong>
                <p>{item.summary || '案件概要は登録されていません。'}</p>
              </button>
              <footer>
                <span><b>{item.deadline_count || 0}</b> 期限</span>
                <span><b>{item.pending_approval_count}</b> 承認待ち</span>
                <div><button onClick={() => onOpenCase(item.id, 'documents')} type="button">資料登録</button><button className="primary" onClick={() => onOpenCase(item.id, 'assistant')} type="button">書類作成</button></div>
              </footer>
            </article>
          ))}
        </div> : <div className="wk-dashboard-empty"><span><WorkspaceIcon name="case" /></span><h2>担当案件はありません</h2><p>案件を作成すると、資料登録と書類作成を開始できます。</p><button className="wk-primary" onClick={onCreateCase} type="button">案件を作成</button></div>}
      </section>
    </div>
  )
}

export function OverviewView({ caseId, currentUser, onChanged, onNavigate }: { caseId: string; currentUser: User | null; onChanged: () => void; onNavigate: (view: WorkspaceView) => void }) {
  const [overview, setOverview] = useState<CaseOverview | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.overview(caseId).then(setOverview).catch((caught) => setError(errorMessage(caught)))
  }, [caseId])

  if (!overview) return <ViewLoading error={error} label="案件情報を読み込んでいます" />
  const stats = [
    ['期限', overview.case.deadline_count || 0, '未完了の締め切り'],
    ['作成結果', overview.stats.messages, '書類案と整合性確認'],
    ['承認待ち', overview.stats.pending_approvals, '責任者の確認が必要'],
    ['操作履歴', overview.stats.audit_events, 'この案件の操作記録'],
  ]
  return (
    <div className="wk-view wk-overview">
      <div className="wk-view-heading">
        <div><p className="wk-eyebrow">案件情報</p><h1>{overview.case.name}</h1><p>依頼人・対象者：{overview.case.client_name}<br />{overview.case.summary || '案件概要は登録されていません。'}</p></div>
        <button className="wk-primary" onClick={() => onNavigate('assistant')} type="button">書類作成</button>
      </div>

      <div className="wk-stat-grid">
        {stats.map(([label, value, note]) => <article key={String(label)}><small>{label}</small><strong>{value}</strong><span>{note}</span></article>)}
      </div>

      <section className="wk-section">
        <header><div><p className="wk-eyebrow">作業</p><h2>作業を開始</h2></div><button className="wk-text-button" onClick={() => onNavigate('documents')} type="button">資料管理</button></header>
        <div className="wk-workflow-grid">
          {taskOptions.map((task) => (
            <button key={task.id} onClick={() => onNavigate('assistant')} type="button">
              <span>{task.icon}</span><h3>{task.title}</h3><p>{task.description}</p><b>開始</b>
            </button>
          ))}
        </div>
      </section>

      <div className="wk-overview-split">
        <section className="wk-panel">
          <header><div><p className="wk-eyebrow">作成履歴</p><h2>最近の作成結果</h2></div><button className="wk-text-button" onClick={() => onNavigate('assistant')} type="button">書類作成</button></header>
          <div className="wk-latest-list">
            {overview.latest_messages.length ? overview.latest_messages.map((message) => (
              <article key={message.id}><span>✦</span><div><strong>{message.payload?.title || normalizeStoredMessageCopy(message.content)}</strong><small>{taskLabel(message.task_type)}・{formatDate(message.created_at)}</small></div><b>{messageStatusLabel(message.status)}</b></article>
            )) : <EmptyState title="作成結果はありません" text="書類案の作成または整合性確認を開始してください。" />}
          </div>
        </section>
        <section className="wk-panel wk-next-panel">
          <p className="wk-eyebrow">承認待ち</p><h2>作成結果を確認</h2>
          <p>内容と参照資料を確認し、承認または差戻しを行います。</p>
          <button onClick={() => onNavigate('approvals')} type="button">確認・承認</button>
        </section>
      </div>

      <CaseMembersPanel caseId={caseId} currentUser={currentUser} onChanged={onChanged} />

    </div>
  )
}

function NewCaseForm({ onCreated }: { onCreated: (caseId: string) => void }) {
  const [name, setName] = useState('')
  const [clientName, setClientName] = useState('')
  const [summary, setSummary] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const created = await api.createCase({ name, client_name: clientName, summary })
      onCreated(created.id)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="wk-new-case-form" onSubmit={(event) => void submit(event)}>
      <label><span>案件名</span><input onChange={(event) => setName(event.target.value)} placeholder="例：B社 業務委託契約の確認" required value={name} /></label>
      <label><span>依頼人・対象者</span><input onChange={(event) => setClientName(event.target.value)} placeholder="例：B社／対象者A" required value={clientName} /></label>
      <label className="wide"><span>案件概要</span><textarea onChange={(event) => setSummary(event.target.value)} placeholder="依頼内容、期限、確認事項" value={summary} /></label>
      {error && <p className="wk-form-error">{error}</p>}
      <button className="wk-primary" disabled={busy} type="submit">{busy ? '作成中…' : '案件を作成'}</button>
    </form>
  )
}

function CalendarView({ caseId, currentUser, onChanged }: { caseId: string; currentUser: User | null; onChanged: () => void }) {
  const [deadlines, setDeadlines] = useState<Deadline[]>([])
  const [weekCursor, setWeekCursor] = useState(() => new Date())
  const [googleSyncPreview, setGoogleSyncPreview] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [title, setTitle] = useState('')
  const [dueDate, setDueDate] = useState('2026-09-25')
  const [kind, setKind] = useState<Deadline['kind']>('internal')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const next = await api.deadlines(caseId)
      setDeadlines(next)
      setError('')
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }, [caseId])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const weekDays = useMemo(() => {
    const firstDay = new Date(weekCursor.getFullYear(), weekCursor.getMonth(), weekCursor.getDate())
    firstDay.setDate(firstDay.getDate() - ((firstDay.getDay() + 6) % 7))
    return Array.from({ length: 7 }, (_, index) => {
      const date = new Date(firstDay)
      date.setDate(firstDay.getDate() + index)
      return date
    })
  }, [weekCursor])

  const openDeadlines = deadlines.filter((deadline) => deadline.status === 'open')
  const overdueCount = openDeadlines.filter((deadline) => deadline.due_date < localDateKey(new Date())).length

  async function createDeadline(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!title.trim() || !currentUser || busy) return
    setBusy(true)
    setError('')
    try {
      await api.createDeadline(caseId, { title: title.trim(), due_date: dueDate, kind, owner_id: currentUser.id, note })
      setTitle('')
      setNote('')
      setShowForm(false)
      await load()
      onChanged()
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function toggleDeadline(deadline: Deadline) {
    try {
      await api.updateDeadline(deadline.id, { status: deadline.status === 'completed' ? 'open' : 'completed' })
      await load()
      onChanged()
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }

  function moveWeek(offset: number) {
    setWeekCursor((current) => new Date(current.getFullYear(), current.getMonth(), current.getDate() + offset * 7))
  }

  return (
    <div className="wk-view wk-calendar-view">
      <div className="wk-view-heading compact">
        <div><p className="wk-eyebrow">期限管理</p><h1>期限・カレンダー</h1><p>案件の締め切りを一覧とカレンダーで確認し、担当者に割り当てます。</p></div>
        <button className="wk-primary" onClick={() => setShowForm((open) => !open)} type="button">＋ 期限を登録</button>
      </div>
      {error && <InlineError text={error} />}
      <div className="wk-deadline-summary"><span><strong>{openDeadlines.length}</strong> 未完了</span><span className={overdueCount ? 'overdue' : ''}><strong>{overdueCount}</strong> 期限超過</span><span><strong>{deadlines.filter((deadline) => deadline.status === 'completed').length}</strong> 完了</span></div>
      <div className="wk-calendar-layout">
        <section className="wk-section wk-calendar-card">
          <header className="wk-calendar-header"><button aria-label="前の週" className="wk-secondary wk-icon-button" onClick={() => moveWeek(-1)} type="button">‹</button><h2>{formatWeekRange(weekDays[0], weekDays[6])}</h2><button className="wk-secondary wk-calendar-today" onClick={() => setWeekCursor(new Date())} type="button">今週</button><button aria-label="次の週" className="wk-secondary wk-icon-button" onClick={() => moveWeek(1)} type="button">›</button></header>
          <div className="wk-calendar-scroll" aria-label="週カレンダー" role="region" tabIndex={0}>
            <div className="wk-calendar-grid">
              {weekDays.map((date) => {
                const key = localDateKey(date)
                const dayDeadlines = deadlines.filter((deadline) => deadline.due_date === key)
                const today = key === localDateKey(new Date())
                return <div className={`wk-calendar-day ${today ? 'today' : ''}`} key={key}><header><span>{['日', '月', '火', '水', '木', '金', '土'][date.getDay()]}</span><time>{date.getDate()}</time></header><div className="wk-calendar-day-events">{dayDeadlines.map((deadline) => <button className={`wk-calendar-event ${deadline.status}`} key={deadline.id} onClick={() => void toggleDeadline(deadline)} title={`${deadline.title}（クリックで${deadline.status === 'completed' ? '未完了に戻す' : '完了にする'}）`} type="button"><i /><span>{deadline.title}</span></button>)}</div></div>
              })}
            </div>
          </div>
        </section>
        <aside className="wk-calendar-side">
          <section className="wk-google-sync-card" aria-label="Googleカレンダー同期設定のモック">
            <span aria-hidden="true" className="wk-google-mark">G</span>
            <div className="wk-google-sync-copy"><div><strong>Googleカレンダー</strong><small>{googleSyncPreview ? '同期イメージ ON' : '未設定'}</small></div><p>案件の期限をGoogleカレンダーに表示する設定</p><span>画面モックです。実際の接続・同期は行いません。</span></div>
            <button aria-checked={googleSyncPreview} aria-label="Googleカレンダー同期の表示イメージを切り替え" className={`wk-sync-toggle ${googleSyncPreview ? 'on' : ''}`} onClick={() => setGoogleSyncPreview((enabled) => !enabled)} role="switch" type="button"><i /></button>
          </section>
          {showForm && <section className="wk-section wk-deadline-form-card"><header><div><p className="wk-eyebrow">新しい期限</p><h2>締め切りを登録</h2></div></header><form className="wk-deadline-form" onSubmit={(event) => void createDeadline(event)}><label><span>期限名</span><input onChange={(event) => setTitle(event.target.value)} placeholder="例：決裁者の確認" required value={title} /></label><label><span>期日</span><input onChange={(event) => setDueDate(event.target.value)} required type="date" value={dueDate} /></label><label><span>区分</span><select onChange={(event) => setKind(event.target.value as Deadline['kind'])} value={kind}>{deadlineKindOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label><span>メモ <small>任意</small></span><textarea onChange={(event) => setNote(event.target.value)} placeholder="確認事項や完了条件" value={note} /></label><button className="wk-primary" disabled={busy} type="submit">{busy ? '登録中…' : '期限を登録'}</button></form></section>}
          <section className="wk-section wk-deadline-list-card"><header><div><p className="wk-eyebrow">締め切り一覧</p><h2>この案件の期限</h2></div><span className="wk-section-count">{deadlines.length}件</span></header><div className="wk-deadline-list">{deadlines.map((deadline) => <article className={deadline.status === 'completed' ? 'completed' : deadline.due_date < localDateKey(new Date()) ? 'overdue' : ''} key={deadline.id}><button aria-label={`${deadline.title}を${deadline.status === 'completed' ? '未完了に戻す' : '完了にする'}`} className="wk-deadline-check" onClick={() => void toggleDeadline(deadline)} type="button">{deadline.status === 'completed' ? '✓' : ''}</button><div><strong>{deadline.title}</strong><small>{formatDeadlineDate(deadline.due_date)}・{deadline.owner_name}・{deadlineKindLabel(deadline.kind)}</small>{deadline.note && <p>{deadline.note}</p>}</div></article>)}{!deadlines.length && <EmptyState title="期限は登録されていません" text="期限を登録すると、担当者と締め切りを共有できます。" />}</div></section>
        </aside>
      </div>
    </div>
  )
}

function CaseChatView({ caseId, currentUser }: { caseId: string; currentUser: User | null }) {
  const [messages, setMessages] = useState<DecisionChatMessage[]>([])
  const [members, setMembers] = useState<CaseMember[]>([])
  const [body, setBody] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const canSend = Boolean(currentUser && currentUser.role !== 'viewer')
  const load = useCallback(async () => {
    try {
      const [nextMessages, caseData] = await Promise.all([api.decisionChat(caseId), api.case(caseId)])
      setMessages(nextMessages)
      setMembers(caseData.members || [])
      setError('')
    } catch (caught) { setError(errorMessage(caught)) }
  }, [caseId])
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])
  async function send(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!body.trim() || !canSend || sending) return
    setSending(true)
    try { await api.sendDecisionChat(caseId, body.trim()); setBody(''); await load() } catch (caught) { setError(errorMessage(caught)) } finally { setSending(false) }
  }

  return (
    <div className="wk-view wk-decision-chat-view">
      <div className="wk-view-heading compact"><div><p className="wk-eyebrow">案件内連絡</p><h1>案件チャット</h1><p>書類案、期限、確認事項について、案件参加者どうしで連絡します。</p></div></div>
      {error && <InlineError text={error} />}
      <section className="wk-chat-card">
        <header className="wk-decision-chat-header"><div><strong>案件参加者 {members.length}人</strong><small>{members.map((member) => `${member.display_name}（${roleLabel(member.role)}）`).join('・') || '参加者情報を読み込んでいます'}</small></div><span className="wk-chat-scope">案件内のみ</span></header>
        <div aria-live="polite" className="wk-decision-chat-messages">{messages.map((message) => {
          const mine = message.author_id === currentUser?.id
          return <article className={mine ? 'mine' : 'received'} key={message.id}>
            {!mine && <span aria-hidden="true" className="wk-chat-avatar">{message.author_name.trim().slice(0, 1)}</span>}
            <div className="wk-chat-message-body"><header><strong>{message.author_name}</strong><small>{roleLabel(message.author_role)}</small></header><p className="wk-chat-bubble-text">{message.body}</p></div>
            <time className="wk-chat-time">{formatTime(message.created_at)}</time>
          </article>
        })}{!messages.length && <EmptyState title="まだメッセージはありません" text="案件参加者へ確認したい内容を送信できます。" />}</div>
        <form className="wk-decision-chat-composer" onSubmit={(event) => void send(event)}><textarea aria-label="案件参加者へのメッセージ" disabled={!canSend || sending} onChange={(event) => setBody(event.target.value)} placeholder={canSend ? '案件参加者へメッセージを入力' : '閲覧権限ではメッセージを送信できません'} value={body} /><button className="wk-primary" disabled={!canSend || sending || !body.trim()} type="submit">送信</button></form>
      </section>
    </div>
  )
}

function CaseMembersPanel({ caseId, currentUser, onChanged }: { caseId: string; currentUser: User | null; onChanged: () => void }) {
  const [caseData, setCaseData] = useState<LegalCase | null>(null)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState('')
  const canManage = currentUser?.role === 'admin'
  const load = useCallback(async () => {
    try { setCaseData(await api.case(caseId)); setError('') } catch (caught) { setError(errorMessage(caught)) }
  }, [caseId])
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])
  if (!caseData) return <section className="wk-section wk-members-section"><ViewLoading error={error} label="参加者情報を読み込んでいます" /></section>

  async function changeAccess(userId: string, accessLevel: CaseMember['access_level']) {
    if (!canManage) return
    setBusyId(userId)
    try { await api.updateCaseMember(caseId, userId, accessLevel); await load(); onChanged() } catch (caught) { setError(errorMessage(caught)) } finally { setBusyId('') }
  }

  return (
    <section className="wk-section wk-members-section">
      <header><div><p className="wk-eyebrow">案件管理</p><h2>参加者と権限</h2></div><span className="wk-section-count">{caseData.members?.length || 0}人</span></header>
      <p className="wk-members-intro">案件参加者の閲覧・編集・確認権限を管理します。業務範囲の確認は、書類作成や承認の操作中に行います。</p>
      {error && <InlineError text={error} />}
      {!canManage && <div className="wk-role-info"><span>i</span><p><strong>現在の権限：{roleLabel(currentUser?.role || 'viewer')}</strong>権限の変更は管理者のみ実行できます。</p></div>}
      <div className="wk-member-list">{(caseData.members || []).map((member) => <div className="wk-member-row" key={member.id}><span className="wk-member-avatar">{member.initials}</span><div><strong>{member.display_name}</strong><small>{roleLabel(member.role)}</small></div><select aria-label={`${member.display_name}の案件権限`} disabled={!canManage || busyId === member.id} onChange={(event) => void changeAccess(member.id, event.target.value as CaseMember['access_level'])} value={member.access_level}>{accessLevelOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>)}</div>
      <p className="wk-members-note">権限変更は操作履歴に記録されます。承認・対外連絡の実行権限は、確認責任者の承認と分けて管理します。</p>
    </section>
  )
}

function DocumentsView({ caseId, onChanged, onNavigate }: { caseId: string; onChanged: () => void; onNavigate: (view: WorkspaceView) => void }) {
  const [documents, setDocuments] = useState<CaseDocument[]>([])
  const [selected, setSelected] = useState<CaseDocument | null>(null)
  const [kind, setKind] = useState('reference')
  const [uploading, setUploading] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try {
      setDocuments(await api.documents(caseId))
      setError('')
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }, [caseId])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  async function upload(file: File | undefined) {
    if (!file) return
    setUploading(true)
    setError('')
    try {
      await api.uploadDocument(caseId, file, kind)
      await load()
      onChanged()
    } catch (caught) {
      setError(errorMessage(caught))
      await load()
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function openDocument(documentId: string) {
    try {
      setSelected(await api.document(documentId))
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }

  async function deleteDocument(document: CaseDocument) {
    if (!window.confirm(`「${document.name}」を削除します。この操作は取り消せません。`)) return
    try {
      await api.deleteDocument(document.id)
      if (selected?.id === document.id) setSelected(null)
      await load()
      onChanged()
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }

  const kindCounts = documents.reduce<Record<string, number>>((counts, document) => ({ ...counts, [document.kind]: (counts[document.kind] || 0) + 1 }), {})
  return (
    <div className="wk-view">
      <div className="wk-view-heading compact">
        <div><p className="wk-eyebrow">案件資料</p><h1>資料管理</h1><p>相談記録、書面案、証拠資料を区分して登録します。</p></div>
      </div>
      {error && <InlineError text={error} />}
      <div className={`wk-doc-toolbar ${dragActive ? 'drag-active' : ''}`} onDragEnter={(event) => { event.preventDefault(); setDragActive(true) }} onDragOver={(event) => event.preventDefault()} onDragLeave={(event) => { if (event.currentTarget === event.target) setDragActive(false) }} onDrop={(event) => { event.preventDefault(); setDragActive(false); void upload(event.dataTransfer.files?.[0]) }}>
        <label><span>資料区分</span><select onChange={(event) => setKind(event.target.value)} value={kind}>{documentKindOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <input accept=".docx,.pdf,.txt" aria-label="資料ファイル" onChange={(event) => void upload(event.target.files?.[0])} ref={fileRef} type="file" />
        <button className="wk-primary" disabled={uploading} onClick={() => fileRef.current?.click()} type="button">{uploading ? '登録中…' : '＋ 資料を登録'}</button>
        <small>{dragActive ? 'ここにドロップ' : 'ファイルをドラッグ＆ドロップできます'}</small>
      </div>
      <div className="wk-format-note"><strong>対応形式</strong><span>DOCX、文字情報を含むPDF、TXT（1ファイル25MBまで）</span></div>
      <div className="wk-doc-stats">
        <span><b>{documents.length}</b> 登録資料</span><span><b>{kindCounts.target_contract || 0}</b> 確認対象</span><span><b>{kindCounts.internal_template || 0}</b> 所内ひな形</span><span><b>{kindCounts.evidence || 0}</b> 証拠資料</span>
      </div>
      <div className="wk-doc-table-wrap">
        <table className="wk-doc-table">
          <thead><tr><th>資料</th><th>区分</th><th>状態</th><th>登録者</th><th>登録日時</th><th>操作</th></tr></thead>
          <tbody>
            {documents.map((document) => (
              <tr key={document.id}>
                <td><button className="wk-doc-name" onClick={() => void openDocument(document.id)} type="button"><i>{fileGlyph(document.name)}</i><span><strong>{document.name}</strong><small>{document.size_label}・{document.chunk_count || 0}箇所</small></span></button></td>
                <td><span className="wk-kind-tag">{documentKindLabel(document.kind)}</span></td>
                <td><span className={`wk-status-dot ${document.status}`}><i />{document.status === 'ready' ? '登録済み' : document.status === 'failed' ? '読取失敗' : '読取中'}</span></td>
                <td>{document.created_by_name || '—'}</td><td>{formatDate(document.created_at)}</td>
                <td><div className="wk-row-actions"><button onClick={() => void openDocument(document.id)} type="button">表示</button><button className="danger" onClick={() => void deleteDocument(document)} type="button">削除</button></div></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!documents.length && <div className="wk-empty-with-action"><EmptyState title="資料は登録されていません" text="確認対象の書面案や参照資料を登録してください。" /><button className="wk-primary" onClick={() => fileRef.current?.click()} type="button">資料を登録</button></div>}
      </div>
      {documents.length > 0 && <div className="wk-next-step"><div><strong>登録資料を使用できます</strong><span>書類案の作成または整合性確認を開始できます。</span></div><button className="wk-primary" onClick={() => onNavigate('assistant')} type="button">書類作成</button></div>}
      {selected && <DocumentDrawer document={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}

function DocumentDrawer({ document, citation, onClose }: { document: CaseDocument; citation?: Citation | null; onClose: () => void }) {
  const citedChunk = citation ? document.chunks?.find((chunk) => chunk.id === citation.chunk_id) : null
  return (
    <div className="wk-drawer-layer">
      <button aria-label="資料を閉じる" className="wk-drawer-scrim" onClick={onClose} type="button" />
      <aside className="wk-document-drawer">
        <header><div><span>{documentKindLabel(document.kind)}</span><h2>{document.name}</h2><small>{document.size_label}・{document.page_count}ページ</small></div><button aria-label="閉じる" onClick={onClose} type="button">×</button></header>
        {document.status === 'failed' ? <InlineError text={document.error || '資料を読み取れませんでした。'} /> : citedChunk ? <div className="wk-document-chunks"><div className="wk-citation-focus"><strong>参照箇所</strong><span>{citation?.locator}</span><p>{citation?.excerpt}</p></div>{document.chunks?.map((chunk) => <article className={chunk.id === citation?.chunk_id ? 'active' : ''} key={chunk.id}><header><span>{chunk.page_number ? `p.${chunk.page_number}` : `#${chunk.chunk_index + 1}`}</span><strong>{chunk.section || '本文'}</strong></header><pre>{chunk.text}</pre></article>)}</div> : <pre>{document.content}</pre>}
        <footer><button onClick={() => void navigator.clipboard.writeText(document.content || '')} type="button">本文をコピー</button></footer>
      </aside>
    </div>
  )
}

function AssistantView({ caseId, onChanged, onNavigate }: { caseId: string; onChanged: () => void; onNavigate: (view: WorkspaceView) => void }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [documents, setDocuments] = useState<CaseDocument[]>([])
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([])
  const [activeTask, setActiveTask] = useState<TaskType>('draft')
  const [draftTitle, setDraftTitle] = useState('調査・確認報告書')
  const [audience, setAudience] = useState('所内確認')
  const [workflowNote, setWorkflowNote] = useState('')
  const [draftVersions, setDraftVersions] = useState<DraftVersion[]>([])
  const [resolutions, setResolutions] = useState<Record<string, Record<number, FindingResolution>>>({})
  const [savedMessageId, setSavedMessageId] = useState('')
  const [question, setQuestion] = useState('')
  const [sending, setSending] = useState(false)
  const [stageIndex, setStageIndex] = useState(0)
  const [error, setError] = useState('')
  const [sourceDocument, setSourceDocument] = useState<{ document: CaseDocument; citation: Citation | null } | null>(null)
  const chatRef = useRef<HTMLDivElement>(null)

  const load = useCallback(async () => {
    try {
      const nextMessages = await api.messages(caseId)
      setMessages(nextMessages)
      const [nextDocuments, nextDrafts] = await Promise.all([api.documents(caseId), api.draftVersions(caseId)])
      setDocuments(nextDocuments)
      setSelectedDocumentIds((existing) => existing.length ? existing.filter((id) => nextDocuments.some((document) => document.id === id)) : nextDocuments.filter((document) => document.status === 'ready').map((document) => document.id))
      setDraftVersions(nextDrafts)
      const findingMessages = nextMessages.filter((message) => message.role === 'assistant' && Boolean(message.payload?.findings.length))
      const nextResolutions = await Promise.all(findingMessages.map(async (message) => [message.id, await api.findingResolutions(message.id)] as const))
      setResolutions(Object.fromEntries(nextResolutions.map(([messageId, items]) => [messageId, Object.fromEntries(items.map((item) => [item.finding_index, item]))])))
      setError('')
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }, [caseId])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])
  useEffect(() => {
    chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sending, stageIndex])

  function buildWorkflowPrompt() {
    const selectedNames = documents.filter((document) => selectedDocumentIds.includes(document.id)).map((document) => document.name)
    const scope = selectedNames.length ? `使用する資料：${selectedNames.join('、')}` : '案件内の登録資料を使用'
    if (activeTask === 'draft') return `${scope}\n書類名：${draftTitle}\n用途：${audience}\n追加条件：${workflowNote || '事実と推測を分け、確認が必要な箇所を明示してください。'}\n\n登録資料をもとに、担当者が修正できる書類案を作成してください。`
    return `${scope}\n確認対象：${draftTitle}\n\n登録資料と書類案を照合し、誤字脱字、氏名、日付、金額、引用箇所、証拠番号の不一致候補を示してください。`
  }

  async function send(customQuestion?: string, taskType: TaskType = 'general') {
    const text = (customQuestion ?? (taskType === 'general' ? question : buildWorkflowPrompt())).trim()
    if (!text || sending) return
    if (taskType !== 'general' && !documents.some((document) => selectedDocumentIds.includes(document.id) && document.status === 'ready')) {
      setError('登録済みの資料を1件以上選択してください。')
      return
    }
    setSending(true)
    setError('')
    setStageIndex(0)
    const timer = window.setInterval(() => setStageIndex((index) => Math.min(index + 1, stages.length - 1)), 650)
    try {
      await api.sendMessage(caseId, text, taskType)
      setQuestion('')
      await load()
      onChanged()
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      window.clearInterval(timer)
      setSending(false)
    }
  }

  async function regenerate(messageId: string) {
    setSending(true)
    setError('')
    try {
      await api.regenerate(messageId)
      await load()
      onChanged()
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setSending(false)
    }
  }

  async function feedback(messageId: string, rating: 'helpful' | 'needs_improvement') {
    try {
      await api.feedback(messageId, rating)
      await load()
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }

  async function openCitation(citation: Citation) {
    try {
      setSourceDocument({ document: await api.document(citation.document_id), citation })
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }

  function selectTask(task: TaskType) {
    setActiveTask(task)
    setError('')
  }

  async function saveDraft(message: Message, content: string) {
    if (!message.payload || !content.trim()) return
    try {
      const saved = await api.saveDraftVersion(caseId, { source_message_id: message.id, title: message.payload.title, content })
      setDraftVersions((items) => [saved, ...items])
      setSavedMessageId(message.id)
      onChanged()
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }

  async function updateFinding(messageId: string, findingIndex: number, status: FindingResolution['status']) {
    try {
      const updated = await api.updateFindingResolution(messageId, findingIndex, { status })
      setResolutions((current) => ({ ...current, [messageId]: { ...(current[messageId] || {}), [findingIndex]: updated } }))
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }

  return (
    <div className="wk-view wk-assistant-view">
      <section className="wk-workflow-setup">
        <div className="wk-workflow-setup-head"><div><p className="wk-eyebrow">書類作成</p><h1>作業条件</h1><p>作業内容と使用する資料を選択してください。</p></div><button className="wk-secondary" onClick={() => onNavigate('documents')} type="button">資料管理</button></div>
        <div className="wk-task-choice">{taskOptions.map((task) => <button className={activeTask === task.id ? 'active' : ''} key={task.id} onClick={() => selectTask(task.id)} type="button"><b>{task.icon}</b><span><strong>{task.title}</strong><small>{task.description}</small></span></button>)}</div>
        <div className="wk-workflow-fields">
          <div className="wk-document-picker"><span>使用する資料 <b>{selectedDocumentIds.length}件</b></span><div>{documents.filter((document) => document.status === 'ready').map((document) => <label key={document.id}><input checked={selectedDocumentIds.includes(document.id)} onChange={(event) => setSelectedDocumentIds((current) => event.target.checked ? [...current, document.id] : current.filter((id) => id !== document.id))} type="checkbox" /><span>{document.name}</span></label>)}</div><button onClick={() => setSelectedDocumentIds(documents.filter((document) => document.status === 'ready').map((document) => document.id))} type="button">すべて選択</button></div>
          <label><span>{activeTask === 'draft' ? '書類名' : '確認対象'}</span><input onChange={(event) => setDraftTitle(event.target.value)} placeholder="例：調査報告書／回答書" value={draftTitle} /></label>
          {activeTask === 'draft' && <label><span>用途</span><select onChange={(event) => setAudience(event.target.value)} value={audience}><option>所内確認</option><option>依頼人への説明</option><option>提出・報告</option></select></label>}
          <label className="wide"><span>追加条件 <small>任意</small></span><input onChange={(event) => setWorkflowNote(event.target.value)} placeholder="期限、文体、確認事項など" value={workflowNote} /></label>
          <button className="wk-primary wk-workflow-run" disabled={sending || !documents.some((document) => selectedDocumentIds.includes(document.id) && document.status === 'ready')} onClick={() => void send(undefined, activeTask)} type="button">{sending ? '処理中…' : activeTask === 'draft' ? '書類案を作成' : '整合性を確認'}</button>
        </div>
        {!documents.length && <div className="wk-workflow-empty"><strong>資料は登録されていません</strong><span>書類作成に使用する資料を登録してください。</span><button onClick={() => onNavigate('documents')} type="button">資料を登録</button></div>}
      </section>
      <section className="wk-chat-panel">
        <header className="wk-chat-header"><div><strong>案件アシスタント</strong></div><span><i />入力待ち</span></header>
        {error && <InlineError text={error} />}
        <div className="wk-focus-strip"><span>作業を切り替える</span>{taskOptions.map((task) => <button className={activeTask === task.id ? 'active' : ''} key={task.id} onClick={() => selectTask(task.id)} type="button"><b>{task.icon}</b><span><strong>{task.title}</strong><small>{task.description}</small></span></button>)}</div>
        <div className="wk-chat-window" ref={chatRef}>
          {!messages.length && <div className="wk-chat-welcome"><span>A</span><h2>作業を開始</h2><p>作業を選択するか、依頼内容を入力してください。</p><div className="wk-starter-prompts"><button onClick={() => void send(taskOptions[0].prompt, 'draft')} type="button">書類案を作成</button><button onClick={() => void send(taskOptions[1].prompt, 'consistency_check')} type="button">整合性を確認</button></div></div>}
          {messages.map((message) => message.role === 'user' ? <UserMessage key={message.id} message={message} /> : (
            <AssistantMessage
              approval={undefined}
              canApprove={false}
              key={message.id}
              message={message}
              onApprove={() => undefined}
              onCitation={openCitation}
              onFeedback={(rating) => void feedback(message.id, rating)}
              onRegenerate={() => void regenerate(message.id)}
              onSaveDraft={(content) => void saveDraft(message, content)}
              onFindingStatus={(findingIndex, status) => void updateFinding(message.id, findingIndex, status)}
              findingResolutions={resolutions[message.id] || {}}
              draftVersions={draftVersions.filter((version) => version.source_message_id === message.id)}
              saved={savedMessageId === message.id}
              onOpenApprovals={() => onNavigate('approvals')}
              onSuggestedAction={(label) => { const task = suggestedTask(label); void send(suggestedPrompt(task), task) }}
            />
          ))}
          {sending && <GenerationProgress stageIndex={stageIndex} />}
        </div>
        <footer className="wk-composer">
          <div className="wk-composer-context"><span>{taskLabel(activeTask)}</span><small>{selectedDocumentIds.length}件の資料を参照</small></div>
          <div className="wk-composer-box"><textarea aria-label="依頼内容" disabled={sending} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') void send() }} placeholder="依頼内容を入力" value={question} /><button aria-label="送信" disabled={sending || !question.trim()} onClick={() => void send()} type="button">↑</button></div>
          <small>⌘またはCtrl＋Enterで送信</small>
        </footer>
      </section>
      {sourceDocument && <DocumentDrawer citation={sourceDocument.citation} document={sourceDocument.document} onClose={() => setSourceDocument(null)} />}
    </div>
  )
}

function UserMessage({ message }: { message: Message }) {
  return <article className="wk-user-message"><div><small>{formatTime(message.created_at)}・{message.created_by_name || 'あなた'}</small><p>{normalizeStoredMessageCopy(message.content)}</p></div><span>{message.initials || 'U'}</span></article>
}

function AssistantMessage({ message, approval, canApprove, onCitation, onFeedback, onRegenerate, onApprove, onSuggestedAction, onSaveDraft, onFindingStatus, findingResolutions, draftVersions, saved, onOpenApprovals }: {
  message: Message
  approval?: Approval
  canApprove: boolean
  onCitation: (citation: Citation) => void
  onFeedback: (rating: 'helpful' | 'needs_improvement') => void
  onRegenerate: () => void
  onApprove: () => void
  onSuggestedAction: (label: string) => void
  onSaveDraft: (content: string) => void
  onFindingStatus: (findingIndex: number, status: FindingResolution['status']) => void
  findingResolutions: Record<number, FindingResolution>
  draftVersions: DraftVersion[]
  saved: boolean
  onOpenApprovals: () => void
}) {
  const payload = message.payload
  const initialDraft = payload?.artifact_type === 'draft' ? payload.blocks.find((block) => ['ドラフト本文', '書類案本文'].includes(block.title))?.content || '' : ''
  const [editedDraft, setEditedDraft] = useState(initialDraft)
  if (!payload) return (
    <article className="wk-ai-message">
      <span>A</span>
      <div className="wk-ai-column">
        <div className="wk-message-meta"><strong>Alteor</strong><small>{formatTime(message.created_at)}</small></div>
        <div className="wk-ai-bubble wk-chat-bubble">
          <p className="wk-chat-content">{normalizeStoredMessageCopy(message.content)}</p>
          {message.citations.length > 0 && <details className="wk-sources"><summary>参照資料 <span>{message.citations.length}件</span></summary><div>{message.citations.map((source, index) => <button key={`${source.chunk_id}-${index}`} onClick={() => onCitation(source)} type="button"><b>{index + 1}</b><span><strong>{source.document_name}</strong><small>{source.locator}</small><p>{source.excerpt}</p></span><i>↗</i></button>)}</div></details>}
          <div className="wk-message-actions">
            <button onClick={() => void navigator.clipboard.writeText(normalizeStoredMessageCopy(message.content))} type="button">回答をコピー</button>
            <button className={message.feedback === 'helpful' ? 'selected' : ''} onClick={() => onFeedback('helpful')} type="button">参考になった</button>
            <button onClick={onRegenerate} type="button">同じ条件で再作成</button>
          </div>
        </div>
      </div>
    </article>
  )
  return (
    <article className="wk-ai-message">
      <span>A</span>
      <div className="wk-ai-column">
        <div className="wk-message-meta"><strong>Alteor</strong><small>{formatTime(message.created_at)}・v{message.version}</small></div>
        <div className="wk-ai-bubble">
          <header><span>{payload.label}</span><h2>{payload.title}</h2>{payload.findings.some((finding) => finding.severity === 'high') && <b>重要度：高</b>}</header>
          <div className="wk-answer-blocks">
            {payload.blocks.map((block, index) => <section className={block.tone || 'neutral'} key={`${block.title}-${index}`}><h3>{block.title}</h3>{block.content && (payload.artifact_type === 'draft' && ['ドラフト本文', '書類案本文'].includes(block.title) ? <textarea className="wk-draft-editor" aria-label="書類案本文" onChange={(event) => setEditedDraft(event.target.value)} value={editedDraft} /> : <p>{block.content}</p>)}{block.items && <ul>{block.items.map((item) => <li key={item}><i>✓</i>{item}</li>)}</ul>}</section>)}
          </div>
          {payload.findings.length > 0 && <details className="wk-findings"><summary>確認事項 <span>{payload.findings.length}件</span></summary>{payload.findings.map((finding, index) => { const resolution = findingResolutions[index]?.status || 'open'; return <article className={resolution} key={`${finding.title}-${index}`}><header><b className={finding.severity}>{finding.severity === 'high' ? '高' : finding.severity === 'medium' ? '中' : '低'}</b><strong>{finding.title}</strong><small>{finding.target}</small><span className="wk-finding-state">{resolution === 'resolved' ? '対応済み' : resolution === 'ignored' ? '対象外' : '要確認'}</span></header><p>{finding.risk}</p><div><b>対応方法</b>{finding.recommendation}</div><footer><button className={resolution === 'open' ? 'active' : ''} onClick={() => onFindingStatus(index, 'open')} type="button">要確認</button><button className={resolution === 'resolved' ? 'active' : ''} onClick={() => onFindingStatus(index, 'resolved')} type="button">対応済み</button><button className={resolution === 'ignored' ? 'active' : ''} onClick={() => onFindingStatus(index, 'ignored')} type="button">対象外</button></footer></article> })}</details>}
          <details className="wk-sources"><summary>参照資料 <span>{payload.sources.length}件</span></summary><div>{payload.sources.map((source, index) => <button key={`${source.chunk_id}-${index}`} onClick={() => onCitation(source)} type="button"><b>{index + 1}</b><span><strong>{source.document_name}</strong><small>{source.locator}</small><p>{source.excerpt}</p></span><i>↗</i></button>)}</div></details>
          <div className="wk-message-actions">
            <button onClick={() => void navigator.clipboard.writeText(answerText(payload, payload.artifact_type === 'draft' ? editedDraft : undefined))} type="button">{payload.artifact_type === 'draft' ? '書類案をコピー' : '結果をコピー'}</button>
            {payload.artifact_type === 'draft' && <button className="save" onClick={() => onSaveDraft(editedDraft)} type="button">{saved ? '新しい版として保存' : '書類案を保存'}</button>}
            <button className={message.feedback === 'helpful' ? 'selected' : ''} onClick={() => onFeedback('helpful')} type="button">参考になった</button>
            <button onClick={onRegenerate} type="button">同じ条件で再作成</button>
            {message.status === 'review_required' && <button className="approve" onClick={onOpenApprovals} type="button">確認・承認</button>}
            {approval?.status === 'pending' && <button className="approve" disabled={!canApprove} onClick={onApprove} title={canApprove ? '' : '確認責任者または管理者が承認します'} type="button">{canApprove ? '確認して承認' : '承認待ち'}</button>}
            {approval && approval.status !== 'pending' && <span className={`wk-approval-state ${approval.status}`}>{approval.status === 'approved' ? '✓ 承認済み' : approval.status === 'executed' ? '✓ 実行済み' : '差戻し'}</span>}
          </div>
          {payload.artifact_type === 'draft' && draftVersions.length > 0 && <details className="wk-draft-history"><summary>保存した版 <span>{draftVersions.length}件</span></summary>{draftVersions.map((version) => <button key={version.id} onClick={() => setEditedDraft(version.content)} type="button"><span>v{version.version}</span><strong>{version.title}</strong><small>{formatDate(version.updated_at)}・{version.created_by_name || '担当者'}</small></button>)}</details>}
        </div>
        {payload.suggested_actions.length > 0 && <div className="wk-suggestions"><span>次の作業</span>{payload.suggested_actions.slice(0, 4).map((action) => <button key={action} onClick={() => onSuggestedAction(action)} type="button">{action}</button>)}</div>}
      </div>
    </article>
  )
}

function GenerationProgress({ stageIndex }: { stageIndex: number }) {
  return <article className="wk-ai-message"><span>A</span><div className="wk-generation"><header><strong>{stages[stageIndex]}</strong><i><i /><i /><i /></i></header><div>{stages.map((stage, index) => <span className={index <= stageIndex ? 'done' : ''} key={stage}><i>{index < stageIndex ? '✓' : index + 1}</i>{stage}</span>)}</div><small>処理しています</small></div></article>
}

export function ApprovalsView({ caseId, currentUser, onChanged }: { caseId: string; currentUser: User | null; onChanged: () => void }) {
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [filter, setFilter] = useState<'all' | 'pending' | 'approved'>('all')
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState('')
  const canApprove = currentUser?.role === 'admin' || currentUser?.role === 'lawyer'
  const load = useCallback(async () => {
    try { setApprovals(await api.approvals(caseId)); setError('') } catch (caught) { setError(errorMessage(caught)) }
  }, [caseId])
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  async function decide(approval: Approval, decision: 'approved' | 'rejected') {
    const comment = decision === 'rejected' ? window.prompt('差戻し理由を入力してください。', '') : '内容と参照資料を確認しました。'
    if (decision === 'rejected' && comment === null) return
    setBusyId(approval.id)
    try {
      await api.decideApproval(approval.id, decision, comment || '')
      await load()
      onChanged()
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusyId('')
    }
  }

  const visible = approvals.filter((approval) => filter === 'all' || (filter === 'approved' ? ['approved', 'executed'].includes(approval.status) : approval.status === filter))
  return (
    <div className="wk-view">
      <div className="wk-view-heading compact"><div><h1>確認・承認</h1><p>作成内容と参照資料を確認し、承認または差戻しを行います。</p></div></div>
      {error && <InlineError text={error} />}
      <div className="wk-filter-tabs">{([['all', 'すべて'], ['pending', '承認待ち'], ['approved', '処理済み']] as const).map(([id, label]) => <button className={filter === id ? 'active' : ''} key={id} onClick={() => setFilter(id)} type="button">{label}<span>{id === 'all' ? approvals.length : approvals.filter((item) => id === 'approved' ? ['approved', 'executed'].includes(item.status) : item.status === id).length}</span></button>)}</div>
      {!canApprove && <div className="wk-role-info"><span>i</span><p><strong>現在の権限：{roleLabel(currentUser?.role || 'viewer')}</strong>この権限では承認・差戻しを実行できません。</p></div>}
      <div className="wk-approval-list">
        {visible.map((approval) => (
          <article key={approval.id}>
            <header><div><span className={`wk-approval-badge ${approval.status}`}>{approvalStatusLabel(approval.status)}</span><small>{artifactLabel(approval.artifact_type)}</small></div><time>{formatDate(approval.created_at)}</time></header>
            <h2>{approval.artifact_payload?.title || connectorActionLabel(approval.artifact_type)}</h2>
            <p>{approval.artifact_payload?.summary || approval.message_content || '内容を確認してください。'}</p>
            <dl><div><dt>作成者</dt><dd>{approval.requested_by_name}</dd></div><div><dt>承認者</dt><dd>{approval.decided_by_name || '未決定'}</dd></div><div><dt>コメント</dt><dd>{approval.comment || '—'}</dd></div></dl>
            {approval.status === 'pending' && <footer><button disabled={!canApprove || busyId === approval.id} onClick={() => void decide(approval, 'rejected')} type="button">差戻し</button><button className="wk-primary" disabled={!canApprove || busyId === approval.id} onClick={() => void decide(approval, 'approved')} type="button">{approval.artifact_type === 'connector_action' ? '承認して実行' : '承認する'}</button></footer>}
          </article>
        ))}
        {!visible.length && <EmptyState title="承認待ちの作成結果はありません" text="書類案や確認結果が作成されると、ここに表示されます。" />}
      </div>
    </div>
  )
}

export function AuditView({ caseId }: { caseId: string }) {
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  useEffect(() => { api.auditEvents(caseId).then(setEvents).catch((caught) => setError(errorMessage(caught))) }, [caseId])
  const visible = useMemo(() => events.filter((event) => `${event.user_name} ${event.event_type} ${auditLabel(event.event_type)} ${event.target_type} ${auditTargetLabel(event.target_type)} ${event.target_id || ''}`.toLowerCase().includes(query.toLowerCase())), [events, query])
  return (
    <div className="wk-view wk-audit-view">
      <div className="wk-audit-heading">
        <div><h1>操作履歴</h1></div>
        <span>全 {events.length} 件</span>
      </div>
      {error && <InlineError text={error} />}
      <div className="wk-audit-toolbar">
        <label>
          <span aria-hidden="true">⌕</span>
          <input aria-label="操作履歴を検索" onChange={(event) => setQuery(event.target.value)} placeholder="実行者、操作、対象で検索" value={query} />
        </label>
        {query && <b>{visible.length} 件</b>}
      </div>
      <div className="wk-audit-table-wrap">
        <table className="wk-audit-table">
          <thead>
            <tr>
              <th>日時</th>
              <th>実行者</th>
              <th>操作</th>
              <th>対象</th>
              <th>結果</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((event) => (
              <tr key={event.id}>
                <td><time>{formatDateTime(event.created_at)}</time></td>
                <td>{event.user_name}</td>
                <td><strong>{auditLabel(event.event_type)}</strong></td>
                <td><span>{auditTargetLabel(event.target_type)}</span>{event.target_id && <small>{event.target_id}</small>}</td>
                <td><span className={`wk-audit-result ${event.result}`}>{event.result === 'success' ? '完了' : '失敗'}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!visible.length && <div className="wk-audit-empty">該当する操作履歴はありません。</div>}
      </div>
    </div>
  )
}

function ViewLoading({ error, label }: { error: string; label: string }) {
  if (error) return <InlineError text={error} />
  return <div className="wk-view-loading"><i /><strong>{label}</strong></div>
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return <div className="wk-empty"><span>◇</span><strong>{title}</strong><p>{text}</p></div>
}

function InlineError({ text }: { text: string }) {
  return <div className="wk-inline-error" role="alert"><span>!</span><p>{text}</p></div>
}

const documentKindOptions = [
  ['target_contract', '確認対象の書面案'], ['internal_template', '所内書式・ひな形'], ['past_review', '過去案件の確認記録'], ['checklist', '確認項目表'], ['consultation', '相談・面談記録'], ['evidence', '証拠・明細資料'], ['email', 'メール・連絡記録'], ['regulation', '規程・参考基準'], ['reference', 'その他の参考資料'],
] as const

const deadlineKindOptions: Array<[Deadline['kind'], string]> = [
  ['court', '裁判所・行政'],
  ['client', '依頼人対応'],
  ['internal', '所内対応'],
  ['other', 'その他'],
]

const accessLevelOptions: Array<[CaseMember['access_level'], string]> = [
  ['owner', '案件責任者'],
  ['reviewer', '確認責任者'],
  ['editor', '編集担当'],
  ['viewer', '閲覧のみ'],
]

function documentKindLabel(kind: string) { return documentKindOptions.find(([value]) => value === kind)?.[1] || '参考資料' }
function deadlineKindLabel(kind: Deadline['kind']) { return deadlineKindOptions.find(([value]) => value === kind)?.[1] || 'その他' }
function caseStatusLabel(status: string) { return ({ preparing: '準備中', active: '進行中', reviewing: '確認中', pending: '対応待ち', pending_approval: '承認待ち', closed: '完了' } as Record<string, string>)[status] || '進行中' }
function taskLabel(task: TaskType) { return taskOptions.find((item) => item.id === task)?.title || ({ clause: '修正文案', mail: '説明メール', checklist: '確認事項', timeline: '時系列表', general: '質問・相談', contract_review: '契約書確認', legal_research: '法令・判例調査', litigation: '紛争整理', client_support: '依頼人対応' } as Record<string, string>)[task] || '質問・相談' }
function roleLabel(role: User['role'] | 'viewer') { return ({ admin: '管理者', lawyer: '確認責任者', staff: '担当者', viewer: '閲覧者' } as const)[role] }
function approvalStatusLabel(status: Approval['status']) { return ({ pending: '承認待ち', approved: '承認済み', rejected: '差戻し', executed: '実行済み' } as const)[status] }
function artifactLabel(type: string) { return ({ draft: '書類案', consistency_check: '整合性確認', review: '契約書確認', research: '調査メモ', litigation: '紛争整理', client_response: '依頼人向け回答', clause: '修正文案', mail: 'メール案', checklist: '確認事項', timeline: '時系列表', connector_action: '連携操作', memo: '案件メモ' } as Record<string, string>)[type] || type }
function connectorActionLabel(type: string) { return type === 'connector_action' ? '連携操作' : '作成結果' }
function fileGlyph(name: string) { return name.toLowerCase().endsWith('.pdf') ? 'P' : name.toLowerCase().endsWith('.docx') ? 'W' : 'T' }
function suggestedTask(label: string): TaskType { if (label.includes('整合') || label.includes('照合')) return 'consistency_check'; if (label.includes('書類案') || label.includes('ドラフト') || label.includes('下書き')) return 'draft'; if (label.includes('修正文') || label.includes('条文')) return 'clause'; if (label.includes('メール') || label.includes('説明文')) return 'mail'; if (label.includes('確認') || label.includes('面談')) return 'checklist'; if (label.includes('時系列') || label.includes('証拠')) return 'timeline'; return 'general' }
function suggestedPrompt(task: TaskType) { return ({ draft: '登録資料をもとに、担当者が修正できる書類案を作成してください。', consistency_check: '登録資料と書類案を照合し、氏名、日付、金額、引用、証拠番号の不一致候補を示してください。', clause: '直前の確認結果をもとに、契約書へ反映できる修正文案と代替案を作成してください。', mail: '直前の結果を説明するメール案を作成してください。', checklist: '回答を確定する前に、依頼人と所内で確認する事項を分けてください。', timeline: '案件資料から日付、当事者、証拠を抽出し、時系列表を作成してください。', general: '直前の回答をもとに、次の作業を整理してください。' } as Record<string, string>)[task] || '続きを整理してください。' }
function answerText(payload: AnswerPayload, draftOverride?: string) { return [payload.title, payload.summary, ...payload.blocks.flatMap((block) => [block.title, ['ドラフト本文', '書類案本文'].includes(block.title) && draftOverride !== undefined ? draftOverride : block.content || '', ...(block.items || [])])].filter(Boolean).join('\n\n') }
function normalizeStoredMessageCopy(value: string) {
  return value
    .replaceAll('ローカルLLMに接続できなかったため、資料検索と規則ベースの下書きを表示しています。', '登録資料をもとに書類案を作成しました。')
    .replaceAll('出力形式：案件資料に基づく書類ドラフト', '書類名：調査・確認報告書')
    .replaceAll('想定読者：所内確認用', '用途：所内確認')
    .replaceAll('確認対象：案件資料に基づく書類ドラフト', '確認対象：調査・確認報告書')
    .replaceAll('登録資料を根拠に、担当者が修正できる書類のドラフトを作成してください。', '登録資料をもとに、担当者が修正できる書類案を作成してください。')
    .replaceAll('登録資料と書類案を照合し、誤字脱字、氏名、日付、金額、引用箇所、証拠番号の不一致を一覧化してください。原文確認が必要な候補として示し、最終判断は担当者が行います。', '登録資料と書類案を照合し、氏名、日付、金額、引用箇所、証拠番号の不一致候補を示してください。')
    .replaceAll('を参照したデモ用初稿です。', 'をもとに作成しました。')
}
function messageStatusLabel(status: string) { return ({ review_required: '未確認', complete: '完了' } as Record<string, string>)[status] || status }
function formatDate(value: string) { return new Intl.DateTimeFormat('ja-JP', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) }
function formatTime(value: string) { return new Intl.DateTimeFormat('ja-JP', { hour: '2-digit', minute: '2-digit' }).format(new Date(value)) }
function formatDeadlineDate(value: string) { return new Intl.DateTimeFormat('ja-JP', { month: 'numeric', day: 'numeric', weekday: 'short' }).format(new Date(`${value}T00:00:00`)) }
function formatWeekRange(start: Date, end: Date) {
  const year = start.getFullYear()
  const endYear = end.getFullYear()
  const startLabel = `${year}年${start.getMonth() + 1}月${start.getDate()}日`
  if (year !== endYear) return `${startLabel}〜${endYear}年${end.getMonth() + 1}月${end.getDate()}日`
  if (start.getMonth() !== end.getMonth()) return `${startLabel}〜${end.getMonth() + 1}月${end.getDate()}日`
  return `${startLabel}〜${end.getDate()}日`
}
function localDateKey(date: Date) { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}` }
function formatDateTime(value: string) { return new Intl.DateTimeFormat('ja-JP', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(value)) }
function auditLabel(event: string) { return ({ 'case.created': '案件を作成', 'case.updated': '案件を更新', 'case.member_updated': '担当者権限を変更', 'document.uploaded': '資料を登録', 'document.viewed': '資料を閲覧', 'document.deleted': '資料を削除', 'document.parse_failed': '資料の読取失敗', 'search.completed': '案件資料を検索', 'generation.completed': '作成処理を実行', 'draft.saved': '書類案を保存', 'finding.updated': '確認事項を更新', 'message.feedback': '回答を評価', 'approval.approved': '作成結果を承認', 'approval.rejected': '作成結果を差戻し', 'deadline.created': '期限を登録', 'deadline.completed': '期限を完了', 'deadline.reopened': '期限を未完了に戻す', 'decision_chat.sent': '案件チャットを送信', 'connector.read': '連携先を参照', 'connector.read_failed': '連携先の参照失敗', 'connector.write_requested': '連携操作の承認を依頼', 'connector.write_failed': '連携操作に失敗', 'connector.configured': '連携設定を変更' } as Record<string, string>)[event] || event }
function auditTargetLabel(target: string) { return ({ case: '案件', document: '資料', message: '作成結果', draft: '書類案', finding: '確認事項', deadline: '期限', decision_chat: '案件チャット', user: '利用者', connector: '連携設定', connector_action: '連携操作' } as Record<string, string>)[target] || target }
function errorMessage(caught: unknown) { return caught instanceof Error ? caught.message : '処理に失敗しました。' }

function WorkspaceIcon({ name }: { name: WorkspaceIconName }) {
  const paths: Record<WorkspaceIconName, React.ReactNode> = {
    home: <><path d="m3 11 9-7 9 7" /><path d="M5 10v10h14V10M9 20v-6h6v6" /></>,
    case: <><rect x="3" y="6" width="18" height="14" rx="2" /><path d="M8 6V4h8v2M3 11h18M10 11v2h4v-2" /></>,
    spark: <><path d="M12 2 9.8 8.8 3 11l6.8 2.2L12 20l2.2-6.8L21 11l-6.8-2.2L12 2Z" /></>,
    documents: <><path d="M6 3h9l3 3v15H6z" /><path d="M15 3v4h4M9 11h6M9 15h6" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18M8 14h3M8 17h6" /></>,
    chat: <><path d="M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H10l-5 3v-3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z" /><path d="M7 10h10M7 14h6" /></>,
    check: <><circle cx="12" cy="12" r="9" /><path d="m8 12 2.5 2.5L16 9" /></>,
    history: <><path d="M4 12a8 8 0 1 0 2.3-5.7L4 8.5" /><path d="M4 4v4.5h4.5M12 7v5l3 2" /></>,
  }
  return <svg aria-hidden="true" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" viewBox="0 0 24 24">{paths[name]}</svg>
}
