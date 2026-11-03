import { CalendarClock, GitBranch, ListChecks, MessageCircleQuestion, ShieldCheck, UserCheck } from 'lucide-react'

import AppShell from '../components/AppShell.jsx'
import AssistantChat, { AssistantIntro } from '../components/assistant/AssistantChat.jsx'
import { useAssistant } from '../components/assistant/AssistantContext.jsx'
import { Card, PageHeader } from '../components/ui.jsx'

const ABILITIES = [
  [ListChecks, 'Status and category/priority', '“Status of SSP-2026-000123”'],
  [CalendarClock, 'TAT and deadline', '“When is the deadline?”'],
  [UserCheck, 'Current authority', '“Who is handling it?”'],
  [GitBranch, 'Escalation and timeline', '“Show the timeline”'],
]

export default function AssistantPage() {
  const assistant = useAssistant()
  return (
    <AppShell>
      <PageHeader
        eyebrow="Help"
        title="SafeSpeak Assistant"
        description="Ask about your complaints in plain language. Every answer is read from SafeSpeak's own records, limited to what your account is allowed to see."
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <section className="card flex h-[calc(100dvh-15rem)] min-h-[440px] flex-col overflow-hidden" aria-label="Conversation">
          <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
            <MessageCircleQuestion className="size-4.5 text-brand-600" aria-hidden="true" />
            <p className="text-sm font-semibold text-slate-900">Conversation</p>
            <div className="ml-auto hidden sm:block">
              <AssistantIntro />
            </div>
          </div>
          <AssistantChat assistant={assistant} autoFocus className="flex-1" />
        </section>
        <div className="stagger space-y-4">
          <Card title="What you can ask" icon={ListChecks}>
            <ul className="space-y-3">
              {ABILITIES.map(([Icon, title, example]) => (
                <li key={title} className="flex gap-3">
                  <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-brand-50 text-brand-600">
                    <Icon className="size-4" aria-hidden="true" />
                  </span>
                  <span className="min-w-0 text-sm">
                    <span className="block font-medium text-slate-800">{title}</span>
                    <button type="button" onClick={() => assistant.send(example.slice(1, -1))} className="-ml-1 inline-flex tap-target items-center rounded px-1 text-left text-xs text-brand-600 hover:underline">
                      {example}
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Private by design" icon={ShieldCheck}>
            <ul className="space-y-2 text-sm text-slate-600">
              <li>• Same access rules as the complaint pages: you only see complaints you may open.</li>
              <li>• An ID you cannot access gets the same answer as one that does not exist.</li>
              <li>• No external AI service; your messages are not stored.</li>
              <li>• It reads records only; it cannot change a complaint.</li>
            </ul>
          </Card>
        </div>
      </div>
    </AppShell>
  )
}
