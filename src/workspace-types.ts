export type UserRole = 'admin' | 'lawyer' | 'staff' | 'viewer'

export type User = {
  id: string
  display_name: string
  initials: string
  role: UserRole
}

export type CaseMember = User & {
  access_level: 'owner' | 'reviewer' | 'editor' | 'viewer'
}

export type LegalCase = {
  id: string
  name: string
  client_name: string
  summary: string
  status: string
  owner_id: string
  document_count: number
  pending_approval_count: number
  deadline_count?: number
  next_deadline_at?: string | null
  next_deadline_title?: string | null
  created_at: string
  updated_at: string
  access_level?: string
  members?: CaseMember[]
}

export type CaseOverview = {
  case: LegalCase
  stats: {
    documents: number
    messages: number
    pending_approvals: number
    audit_events: number
  }
  latest_messages: Message[]
}

export type DeadlineKind = 'court' | 'client' | 'internal' | 'other'

export type Deadline = {
  id: string
  case_id: string
  title: string
  due_date: string
  kind: DeadlineKind
  status: 'open' | 'completed'
  owner_id: string
  owner_name: string
  note: string
  created_by: string
  created_at: string
}

export type DecisionChatMessage = {
  id: string
  case_id: string
  body: string
  author_id: string
  author_name: string
  author_role: UserRole
  created_at: string
}

export type DocumentKind =
  | 'target_contract'
  | 'internal_template'
  | 'past_review'
  | 'checklist'
  | 'consultation'
  | 'evidence'
  | 'email'
  | 'regulation'
  | 'reference'

export type CaseDocument = {
  id: string
  case_id: string
  name: string
  kind: DocumentKind
  mime_type: string
  size_bytes: number
  size_label: string
  page_count: number
  status: 'ready' | 'failed' | 'processing'
  error?: string | null
  content?: string
  chunk_count?: number
  created_by_name?: string
  created_at: string
  chunks?: Array<{
    id: string
    chunk_index: number
    page_number: number | null
    section: string
    text: string
  }>
}

export type Citation = {
  chunk_id: string
  document_id: string
  document_name: string
  locator: string
  excerpt: string
  score: number
}

export type AnswerBlock = {
  title: string
  content?: string | null
  items?: string[] | null
  tone?: 'risk' | 'proposal' | 'neutral'
}

export type Finding = {
  title: string
  severity: 'high' | 'medium' | 'low'
  target: string
  risk: string
  recommendation: string
  draft_clause?: string
  checks?: string[]
}

export type AnswerPayload = {
  label: string
  title: string
  summary: string
  artifact_type: string
  blocks: AnswerBlock[]
  findings: Finding[]
  suggested_actions: string[]
  sources: Citation[]
  notice?: string
}

export type TaskType =
  | 'general'
  | 'draft'
  | 'consistency_check'
  | 'contract_review'
  | 'legal_research'
  | 'litigation'
  | 'client_support'
  | 'clause'
  | 'mail'
  | 'checklist'
  | 'timeline'

export type Message = {
  id: string
  case_id: string
  role: 'user' | 'assistant' | 'system'
  task_type: TaskType
  content: string
  payload: AnswerPayload | null
  citations: Citation[]
  status: string
  model?: string
  parent_id?: string
  version: number
  feedback?: 'helpful' | 'needs_improvement' | null
  feedback_comment?: string | null
  created_by: string
  created_by_name?: string
  initials?: string
  created_at: string
  approval_id?: string
}

export type DraftVersion = {
  id: string
  case_id: string
  source_message_id: string
  version: number
  title: string
  content: string
  status: 'draft' | 'approved'
  created_by: string
  created_by_name?: string
  created_at: string
  updated_at: string
}

export type FindingResolution = {
  finding_index: number
  status: 'open' | 'resolved' | 'ignored'
  note: string
  updated_by?: string
  updated_at?: string
}

export type Approval = {
  id: string
  case_id: string
  artifact_id: string
  artifact_type: string
  artifact_payload: AnswerPayload | null
  message_content?: string | null
  status: 'pending' | 'approved' | 'rejected' | 'executed'
  requested_by: string
  requested_by_name: string
  decided_by?: string | null
  decided_by_name?: string | null
  comment: string
  created_at: string
  decided_at?: string | null
}

export type AuditEvent = {
  id: number
  case_id: string
  user_id: string
  user_name: string
  event_type: string
  target_type: string
  target_id?: string | null
  result: string
  detail: Record<string, unknown>
  created_at: string
}

export type Connector = {
  id: 'calendar' | 'mail' | 'drive' | 'case-db'
  name: string
  kind: 'calendar' | 'mail' | 'drive' | 'database'
  provider: string
  purpose: string
  read_scope: string
  write_scope: string
  mode: 'local' | 'live'
  base_url?: string | null
  token_env?: string | null
  enabled: boolean
  configured: boolean
  external_allowed: boolean
}

export type Health = {
  ok: boolean
  database: { reachable: boolean; path: string }
  prototype: {
    ready: boolean
    mode: 'mock'
    label: string
    description: string
  }
  offline_mode: boolean
  external_connectors_allowed: boolean
  processing_boundary: string
}
