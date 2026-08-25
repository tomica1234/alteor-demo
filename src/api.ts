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
import { demoApi, setDemoUser } from './demo-api'

let activeUserId = window.localStorage.getItem('alteor-user-id') || 'user-admin'
const demoMode = import.meta.env.VITE_DEMO_MODE === 'true'

export function setApiUser(userId: string) {
  activeUserId = userId
  if (demoMode) setDemoUser(userId)
  window.localStorage.setItem('alteor-user-id', userId)
}

export type AccessStatus = { required: boolean; authenticated: boolean }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  headers.set('X-User-Id', activeUserId)
  if (init?.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(`/api${path}`, { ...init, headers, credentials: 'same-origin' })
  if (!response.ok) {
    let message = `処理に失敗しました（${response.status}）`
    try {
      const body = (await response.json()) as { detail?: string | { message?: string } }
      if (typeof body.detail === 'string') message = body.detail
      else if (body.detail?.message) message = body.detail.message
    } catch {
      // The status text is used when a proxy returns a non-JSON error.
      message = response.statusText || message
    }
    throw new Error(message)
  }
  return (await response.json()) as T
}

const backendApi = {
  authStatus: () => request<AccessStatus>('/auth/status'),
  login: (password: string) => request<{ authenticated: boolean }>('/auth/login', { method: 'POST', body: JSON.stringify({ password }) }),
  logout: () => request<{ authenticated: boolean }>('/auth/logout', { method: 'POST' }),
  health: () => request<Health>('/health'),
  users: () => request<User[]>('/users'),
  cases: () => request<LegalCase[]>('/cases'),
  createCase: (body: { name: string; client_name: string; summary: string }) =>
    request<LegalCase>('/cases', { method: 'POST', body: JSON.stringify(body) }),
  case: (caseId: string) => request<LegalCase>(`/cases/${encodeURIComponent(caseId)}`),
  overview: (caseId: string) => request<CaseOverview>(`/cases/${encodeURIComponent(caseId)}/overview`),
  documents: (caseId: string) => request<CaseDocument[]>(`/cases/${encodeURIComponent(caseId)}/documents`),
  document: (documentId: string) => request<CaseDocument>(`/documents/${encodeURIComponent(documentId)}`),
  uploadDocument: (caseId: string, file: File, kind: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('kind', kind)
    return request<CaseDocument>(`/cases/${encodeURIComponent(caseId)}/documents`, { method: 'POST', body: form })
  },
  deleteDocument: (documentId: string) => request<{ ok: boolean }>(`/documents/${encodeURIComponent(documentId)}`, { method: 'DELETE' }),
  messages: (caseId: string) => request<Message[]>(`/cases/${encodeURIComponent(caseId)}/messages`),
  sendMessage: (caseId: string, question: string, taskType: TaskType) =>
    request<Message>(`/cases/${encodeURIComponent(caseId)}/messages`, {
      method: 'POST',
      body: JSON.stringify({ question, task_type: taskType }),
    }),
  regenerate: (messageId: string) => request<Message>(`/messages/${encodeURIComponent(messageId)}/regenerate`, { method: 'POST' }),
  feedback: (messageId: string, rating: 'helpful' | 'needs_improvement') =>
    request<{ ok: boolean }>(`/messages/${encodeURIComponent(messageId)}/feedback`, {
      method: 'POST',
      body: JSON.stringify({ rating, comment: '' }),
    }),
  draftVersions: (caseId: string, sourceMessageId?: string) => request<DraftVersion[]>(`/cases/${encodeURIComponent(caseId)}/drafts${sourceMessageId ? `?source_message_id=${encodeURIComponent(sourceMessageId)}` : ''}`),
  saveDraftVersion: (caseId: string, body: { source_message_id: string; title: string; content: string }) =>
    request<DraftVersion>(`/cases/${encodeURIComponent(caseId)}/drafts`, { method: 'POST', body: JSON.stringify(body) }),
  findingResolutions: (messageId: string) => request<FindingResolution[]>(`/messages/${encodeURIComponent(messageId)}/findings`),
  updateFindingResolution: (messageId: string, findingIndex: number, body: { status: FindingResolution['status']; note?: string }) =>
    request<FindingResolution>(`/messages/${encodeURIComponent(messageId)}/findings/${findingIndex}`, { method: 'PUT', body: JSON.stringify(body) }),
  approvals: (caseId: string) => request<Approval[]>(`/cases/${encodeURIComponent(caseId)}/approvals`),
  decideApproval: (approvalId: string, decision: 'approved' | 'rejected', comment = '') =>
    request<{ ok: boolean; status: string }>(`/approvals/${encodeURIComponent(approvalId)}/decision`, {
      method: 'POST',
      body: JSON.stringify({ decision, comment }),
    }),
  auditEvents: (caseId: string) => request<AuditEvent[]>(`/cases/${encodeURIComponent(caseId)}/audit-events`),
  connectors: () => request<Connector[]>('/connectors'),
  connectorAction: (
    caseId: string,
    connectorId: string,
    actionType: 'read' | 'write',
    operation: string,
    payload: Record<string, unknown>,
  ) =>
    request<{ id: string; status: string; result?: Record<string, unknown>; approval_id?: string; requires_approval: boolean }>(
      `/cases/${encodeURIComponent(caseId)}/connectors/${encodeURIComponent(connectorId)}/actions`,
      { method: 'POST', body: JSON.stringify({ action_type: actionType, operation, payload }) },
    ),
  updateConnector: (
    connectorId: string,
    body: { mode: 'local' | 'live'; provider: string; base_url?: string | null; token_env?: string | null; enabled: boolean },
  ) => request<Connector>(`/connectors/${encodeURIComponent(connectorId)}`, { method: 'PATCH', body: JSON.stringify(body) }),
}

export const api = demoMode ? demoApi : backendApi
