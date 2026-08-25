import type {
  Approval,
  AuditEvent,
  CaseDocument,
  CaseOverview,
  Connector,
  DraftVersion,
  FindingResolution,
  Health,
  LegalCase,
  Message,
  TaskType,
  User,
} from './workspace-types'

const STORAGE_KEY = 'alteor-pages-demo-state-v1'
const AUTH_KEY = 'alteor-pages-demo-auth'
const DEMO_PASSWORD_HASH = import.meta.env.VITE_DEMO_PASSWORD_HASH || ''

let currentUserId = 'user-admin'

type DemoState = {
  users: User[]
  cases: LegalCase[]
  documents: CaseDocument[]
  messages: Message[]
  drafts: DraftVersion[]
  resolutions: Record<string, FindingResolution[]>
  approvals: Approval[]
  auditEvents: AuditEvent[]
  connectors: Connector[]
}

const DEMO_TIME = '2026-07-31T10:28:00.000Z'

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function now() {
  return new Date().toISOString()
}

function id(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 9)}`
}

function chunk(documentId: string, index: number, text: string, section: string) {
  return { id: `${documentId}-chunk-${index}`, chunk_index: index, page_number: 1, section, text }
}

function initialState(): DemoState {
  const users: User[] = [
    { id: 'user-admin', display_name: '橘 駿太', initials: 'ST', role: 'admin' },
    { id: 'user-lawyer', display_name: '佐藤 裕子', initials: 'YS', role: 'lawyer' },
    { id: 'user-staff', display_name: '山田 花子', initials: 'HY', role: 'staff' },
  ]
  const documents: CaseDocument[] = [
    {
      id: 'doc-nda-target', case_id: 'C-2026-0710', name: '提出書面案_事実関係整理.txt', kind: 'target_contract', mime_type: 'text/plain', size_bytes: 470, size_label: '470 B', page_count: 1, status: 'ready', chunk_count: 2, created_by_name: '橘 駿太', created_at: DEMO_TIME,
      content: '提出書面案（確認前）\n\n依頼人は2026年7月15日に初回相談を行った。\n相手方への支払額は3,000,000円であり、2026年7月20日までに返金される予定だった。\n\n提出書面では、相談記録を甲第1号証、振込明細を甲第2号証として引用する。\n\n確認事項: 当事者氏名、相談日、支払額、返金期限、証拠番号。',
      chunks: [chunk('doc-nda-target', 0, '提出書面案（確認前）\n\n依頼人は2026年7月15日に初回相談を行った。\n相手方への支払額は3,000,000円であり、2026年7月20日までに返金される予定だった。', '事実関係'), chunk('doc-nda-target', 1, '提出書面では、相談記録を甲第1号証、振込明細を甲第2号証として引用する。\n\n確認事項: 当事者氏名、相談日、支払額、返金期限、証拠番号。', '証拠番号・確認事項')],
    },
    {
      id: 'doc-nda-template', case_id: 'C-2026-0710', name: '依頼人_初回面談記録.txt', kind: 'consultation', mime_type: 'text/plain', size_bytes: 350, size_label: '350 B', page_count: 1, status: 'ready', chunk_count: 2, created_by_name: '橘 駿太', created_at: DEMO_TIME,
      content: '初回面談記録\n\n面談日時: 2026年7月15日 14時00分\n依頼人は、2026年7月14日に相手方へ3,000,000円を振り込んだと説明した。\n返金期限は2026年7月31日と認識している。\n\n次の対応\n振込原本、相手方との連絡履歴、返金期限を合意した資料を確認する。',
      chunks: [chunk('doc-nda-template', 0, '初回面談記録\n\n面談日時: 2026年7月15日 14時00分\n依頼人は、2026年7月14日に相手方へ3,000,000円を振り込んだと説明した。\n返金期限は2026年7月31日と認識している。', '面談内容'), chunk('doc-nda-template', 1, '次の対応\n振込原本、相手方との連絡履歴、返金期限を合意した資料を確認する。', '次の対応')],
    },
    {
      id: 'doc-review-history', case_id: 'C-2026-0710', name: '銀行取引明細_確認用抜粋.txt', kind: 'evidence', mime_type: 'text/plain', size_bytes: 260, size_label: '260 B', page_count: 1, status: 'ready', chunk_count: 1, created_by_name: '橘 駿太', created_at: DEMO_TIME,
      content: '銀行取引明細（確認用抜粋）\n\n取引日: 2026年7月14日\n振込先: 相手方名義口座\n振込額: 2,800,000円\n摘要: 貸付金\n\nPDF原本との照合前に転記したデータ。提出前に原本と照合すること。',
      chunks: [chunk('doc-review-history', 0, '銀行取引明細（確認用抜粋）\n\n取引日: 2026年7月14日\n振込先: 相手方名義口座\n振込額: 2,800,000円\n摘要: 貸付金\n\nPDF原本との照合前に転記したデータ。提出前に原本と照合すること。', '取引明細')],
    },
    {
      id: 'doc-nda-checklist', case_id: 'C-2026-0710', name: '提出前チェックリスト.txt', kind: 'checklist', mime_type: 'text/plain', size_bytes: 290, size_label: '290 B', page_count: 1, status: 'ready', chunk_count: 1, created_by_name: '橘 駿太', created_at: DEMO_TIME,
      content: '提出前チェックリスト\n\n1. 当事者氏名と住所が原資料と一致しているか。\n2. 日付と時系列が相談記録・証拠資料と一致しているか。\n3. 金額と計算根拠が銀行明細と一致しているか。\n4. 引用箇所と証拠番号が対応しているか。\n5. 最終判断と表現を担当者が確認したか。',
      chunks: [chunk('doc-nda-checklist', 0, '提出前チェックリスト\n\n1. 当事者氏名と住所が原資料と一致しているか。\n2. 日付と時系列が相談記録・証拠資料と一致しているか。\n3. 金額と計算根拠が銀行明細と一致しているか。\n4. 引用箇所と証拠番号が対応しているか。\n5. 最終判断と表現を担当者が確認したか。', '提出前確認')],
    },
  ]
  return {
    users,
    cases: [{ id: 'C-2026-0710', name: '金銭返還／事実関係整理', client_name: '山田 太郎', summary: '相談記録、提出書面、銀行取引明細の内容を照合し、事実関係を整理する。', status: 'reviewing', owner_id: 'user-admin', document_count: documents.length, pending_approval_count: 0, created_at: DEMO_TIME, updated_at: DEMO_TIME }],
    documents,
    messages: [],
    drafts: [],
    resolutions: {},
    approvals: [],
    auditEvents: [{ id: 1, case_id: 'C-2026-0710', user_id: 'user-admin', user_name: '橘 駿太', event_type: 'case.created', target_type: 'case', target_id: 'C-2026-0710', result: 'success', detail: {}, created_at: DEMO_TIME }],
    connectors: [],
  }
}

function readState(): DemoState {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    return stored ? JSON.parse(stored) as DemoState : initialState()
  } catch {
    return initialState()
  }
}

const state = readState()

function save() {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
}

function user() {
  return state.users.find((item) => item.id === currentUserId) || state.users[0]
}

function cite(document: CaseDocument, chunkIndex = 0, score = 0.96) {
  const selected = document.chunks?.[chunkIndex] || document.chunks?.[0]
  return selected ? { chunk_id: selected.id, document_id: document.id, document_name: document.name, locator: `p.${selected.page_number || 1}・${selected.section || '本文'}`, excerpt: selected.text.slice(0, 180), score } : null
}

function caseWithCounts(item: LegalCase): LegalCase {
  return { ...item, document_count: state.documents.filter((document) => document.case_id === item.id).length, pending_approval_count: state.approvals.filter((approval) => approval.case_id === item.id && approval.status === 'pending').length }
}

function citationsFor(caseId: string) {
  return state.documents.filter((document) => document.case_id === caseId && document.status === 'ready').slice(0, 3).map((document, index) => cite(document, 0, 0.96 - index * 0.04)).filter((item): item is NonNullable<typeof item> => Boolean(item))
}

function generatePayload(caseId: string, taskType: TaskType, question: string) {
  const documents = state.documents.filter((document) => document.case_id === caseId && document.status === 'ready')
  const sources = citationsFor(caseId)
  if (taskType === 'consistency_check') {
    return {
      label: '整合性確認', title: '提出前の整合性確認結果', summary: '書面案と登録資料を照合しました。金額と返金期限について、原資料への確認が必要です。', artifact_type: 'consistency_check',
      blocks: [
        { title: '確認結果', content: '氏名と取引日は登録資料の記載と一致しています。一方、書面案の支払額と返金期限は、別の資料に記載された内容と一致していません。' },
        { title: '確認の進め方', items: ['銀行取引明細の原本で振込額を確認する。', '相手方との連絡履歴で返金期限の合意内容を確認する。', '確認後、提出書面案の金額と日付を修正する。'], tone: 'proposal' as const },
      ],
      findings: [
        { title: '振込額が資料間で一致していません', severity: 'high' as const, target: '提出書面案／銀行取引明細', risk: '提出書面案は3,000,000円、銀行取引明細の確認用抜粋は2,800,000円となっています。', recommendation: '振込原本を確認し、確定した金額に統一してください。', checks: ['振込原本の金額', '転記ミスの有無'] },
        { title: '返金期限の記載が一致していません', severity: 'medium' as const, target: '提出書面案／初回面談記録', risk: '提出書面案は2026年7月20日、初回面談記録は2026年7月31日と記載されています。', recommendation: '合意を確認できる連絡履歴を参照し、期限の根拠を明記してください。', checks: ['連絡履歴', '合意日と期限'] },
      ],
      suggested_actions: ['確認事項を整理する', '書類案を作成する'], sources, notice: '確認結果は登録資料の照合に基づく候補です。最終判断は担当者が行ってください。', question,
    }
  }
  const draftText = '調査・確認報告書（案）\n\n1. 相談内容\n依頼人から、相手方への支払および返金に関する経緯について相談を受けた。\n\n2. 現時点で確認できる事実\n依頼人は2026年7月14日に相手方へ金銭を振り込んだと説明している。初回面談は2026年7月15日に行われた。\n\n3. 資料との照合結果\n提出書面案には支払額を3,000,000円と記載しているが、登録された銀行取引明細の確認用抜粋には2,800,000円と記載されている。また、返金期限についても資料間で記載が分かれている。\n\n4. 今後の確認事項\n振込原本、相手方との連絡履歴、返金期限を合意した資料を確認したうえで、金額・期限・証拠番号を確定する。'
  return {
    label: '書類案', title: '調査・確認報告書（案）', summary: '登録資料をもとに、所内確認用の書類案を作成しました。金額と返金期限は提出前に原資料と照合してください。', artifact_type: 'draft',
    blocks: [{ title: '書類案本文', content: draftText }, { title: '作成時の注意', items: ['金額は銀行取引明細の原本と照合する。', '返金期限は相手方との連絡履歴で確認する。', '提出前に担当者が氏名、日付、証拠番号を確認する。'], tone: 'risk' as const }], findings: [], suggested_actions: ['整合性を確認する', '書類案を保存する'], sources, notice: 'この文章は登録資料をもとにした確認用の案です。提出前に原資料と照合してください。', question, documents,
  }
}

function createMessages(caseId: string, question: string, taskType: TaskType): Message[] {
  const createdAt = now()
  const current = user()
  const userMessage: Message = { id: id('msg'), case_id: caseId, role: 'user', task_type: taskType, content: question, payload: null, citations: [], status: 'complete', version: 1, created_by: current.id, created_by_name: current.display_name, initials: current.initials, created_at: createdAt }
  const payload = taskType === 'general' ? null : generatePayload(caseId, taskType, question)
  const assistant: Message = { id: id('msg'), case_id: caseId, role: 'assistant', task_type: taskType, content: payload ? payload.summary : '登録資料を確認しました。次に行う作業を指定してください。', payload, citations: payload?.sources || [], status: payload ? 'review_required' : 'complete', model: 'Alteor mock', version: 1, created_by: 'user-admin', created_by_name: 'Alteor', initials: 'A', created_at: createdAt }
  state.messages.push(userMessage, assistant)
  if (payload) {
    state.approvals.unshift({ id: id('approval'), case_id: caseId, artifact_id: assistant.id, artifact_type: payload.artifact_type, artifact_payload: clone(payload), message_content: assistant.content, status: 'pending', requested_by: current.id, requested_by_name: current.display_name, decided_by: null, decided_by_name: null, comment: '', created_at: createdAt, decided_at: null })
  }
  state.auditEvents.unshift({ id: Date.now(), case_id: caseId, user_id: current.id, user_name: current.display_name, event_type: 'generation.completed', target_type: 'message', target_id: assistant.id, result: 'success', detail: { task_type: taskType }, created_at: createdAt })
  save()
  return [userMessage, assistant]
}

async function hash(value: string) {
  const bytes = new TextEncoder().encode(value)
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, '0')).join('')
}

export function setDemoUser(userId: string) {
  currentUserId = userId
}

export const demoApi = {
  authStatus: async () => ({ required: Boolean(DEMO_PASSWORD_HASH), authenticated: !DEMO_PASSWORD_HASH || window.sessionStorage.getItem(AUTH_KEY) === 'ok' }),
  login: async (password: string) => {
    if (DEMO_PASSWORD_HASH && await hash(password) !== DEMO_PASSWORD_HASH) throw new Error('パスワードが正しくありません。')
    window.sessionStorage.setItem(AUTH_KEY, 'ok')
    return { authenticated: true }
  },
  logout: async () => { window.sessionStorage.removeItem(AUTH_KEY); return { authenticated: false } },
  health: async (): Promise<Health> => ({ ok: true, database: { reachable: false, path: 'browser storage' }, prototype: { ready: true, mode: 'mock', label: 'デモモード', description: 'ブラウザ内の固定データを使用しています。' }, offline_mode: true, external_connectors_allowed: false, processing_boundary: 'browser_demo' }),
  users: async () => clone(state.users),
  cases: async () => clone(state.cases.map(caseWithCounts)),
  createCase: async (body: { name: string; client_name: string; summary: string }) => {
    const item: LegalCase = { id: `C-2026-${Math.floor(Math.random() * 9000 + 1000)}`, ...body, status: 'preparing', owner_id: currentUserId, document_count: 0, pending_approval_count: 0, created_at: now(), updated_at: now() }
    state.cases.unshift(item)
    state.auditEvents.unshift({ id: Date.now(), case_id: item.id, user_id: currentUserId, user_name: user().display_name, event_type: 'case.created', target_type: 'case', target_id: item.id, result: 'success', detail: {}, created_at: now() })
    save()
    return clone(item)
  },
  case: async (caseId: string) => clone(caseWithCounts(state.cases.find((item) => item.id === caseId) || state.cases[0])),
  overview: async (caseId: string): Promise<CaseOverview> => ({ case: clone(caseWithCounts(state.cases.find((item) => item.id === caseId) || state.cases[0])), stats: { documents: state.documents.filter((item) => item.case_id === caseId).length, messages: state.messages.filter((item) => item.case_id === caseId).length, pending_approvals: state.approvals.filter((item) => item.case_id === caseId && item.status === 'pending').length, audit_events: state.auditEvents.filter((item) => item.case_id === caseId).length }, latest_messages: clone(state.messages.filter((item) => item.case_id === caseId && item.role === 'assistant').slice(-3).reverse()) }),
  documents: async (caseId: string) => clone(state.documents.filter((item) => item.case_id === caseId)),
  document: async (documentId: string) => clone(state.documents.find((item) => item.id === documentId) || state.documents[0]),
  uploadDocument: async (caseId: string, file: File, kind: string) => {
    const content = file.type.startsWith('text/') ? await file.text() : `「${file.name}」を登録しました。デモでは本文の読取結果を表示しています。`
    const documentId = id('doc')
    const item: CaseDocument = { id: documentId, case_id: caseId, name: file.name, kind: kind as CaseDocument['kind'], mime_type: file.type || 'application/octet-stream', size_bytes: file.size, size_label: `${Math.max(1, Math.ceil(file.size / 1024))} KB`, page_count: 1, status: 'ready', chunk_count: 1, created_by_name: user().display_name, created_at: now(), content, chunks: [chunk(documentId, 0, content, '本文')] }
    state.documents.unshift(item)
    save()
    return clone(item)
  },
  deleteDocument: async (documentId: string) => { state.documents = state.documents.filter((item) => item.id !== documentId); save(); return { ok: true } },
  messages: async (caseId: string) => clone(state.messages.filter((item) => item.case_id === caseId)),
  sendMessage: async (caseId: string, question: string, taskType: TaskType) => clone(createMessages(caseId, question, taskType)[1]),
  regenerate: async (messageId: string) => {
    const original = state.messages.find((item) => item.id === messageId)
    if (!original) throw new Error('作成結果が見つかりません。')
    return clone(createMessages(original.case_id, original.content, original.task_type)[1])
  },
  feedback: async (messageId: string, rating: 'helpful' | 'needs_improvement') => { const item = state.messages.find((message) => message.id === messageId); if (item) item.feedback = rating; save(); return { ok: true } },
  draftVersions: async (caseId: string, sourceMessageId?: string) => clone(state.drafts.filter((item) => item.case_id === caseId && (!sourceMessageId || item.source_message_id === sourceMessageId)).sort((a, b) => b.version - a.version)),
  saveDraftVersion: async (caseId: string, body: { source_message_id: string; title: string; content: string }) => { const versions = state.drafts.filter((item) => item.source_message_id === body.source_message_id); const item: DraftVersion = { id: id('draft'), case_id: caseId, source_message_id: body.source_message_id, version: versions.length + 1, title: body.title, content: body.content, status: 'draft', created_by: currentUserId, created_by_name: user().display_name, created_at: now(), updated_at: now() }; state.drafts.unshift(item); save(); return clone(item) },
  findingResolutions: async (messageId: string) => clone(state.resolutions[messageId] || []),
  updateFindingResolution: async (messageId: string, findingIndex: number, body: { status: FindingResolution['status']; note?: string }) => { const item = { finding_index: findingIndex, status: body.status, note: body.note || '', updated_by: currentUserId, updated_at: now() }; state.resolutions[messageId] = [...(state.resolutions[messageId] || []).filter((entry) => entry.finding_index !== findingIndex), item]; save(); return clone(item) },
  approvals: async (caseId: string) => clone(state.approvals.filter((item) => item.case_id === caseId)),
  decideApproval: async (approvalId: string, decision: 'approved' | 'rejected', comment = '') => { const item = state.approvals.find((approval) => approval.id === approvalId); if (!item) throw new Error('確認対象が見つかりません。'); item.status = decision; item.comment = comment; item.decided_by = currentUserId; item.decided_by_name = user().display_name; item.decided_at = now(); const message = state.messages.find((entry) => entry.id === item.artifact_id); if (message) message.status = decision === 'approved' ? 'complete' : 'review_required'; save(); return { ok: true, status: item.status } },
  auditEvents: async (caseId: string) => clone(state.auditEvents.filter((item) => item.case_id === caseId).sort((a, b) => b.id - a.id)),
  connectors: async () => clone(state.connectors),
  connectorAction: async () => ({ id: id('connector'), status: 'executed', result: {}, requires_approval: false }),
  updateConnector: async (connectorId: string, body: { mode: 'local' | 'live'; provider: string; base_url?: string | null; token_env?: string | null; enabled: boolean }) => { const item = state.connectors.find((connector) => connector.id === connectorId); if (!item) throw new Error('連携設定が見つかりません。'); Object.assign(item, body); save(); return clone(item) },
}
