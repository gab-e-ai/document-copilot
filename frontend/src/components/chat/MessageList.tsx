import type { UIMessage } from '@ai-sdk/react'
import { CitationCard } from './CitationCard'

interface CitationData {
  chunk_id: string
  excerpt: string
  company: string
  filing_type: string
  filing_date: string
  accession_number: string
}

interface Props {
  messages: UIMessage[]
}

function extractCitations(message: UIMessage): CitationData[] {
  if (message.role !== 'assistant') return []
  // Citations arrive as an AI SDK v5+ data part: { type: 'data-citations', data: { citations } }.
  for (const part of message.parts as Array<{ type: string; data?: { citations?: CitationData[] } }>) {
    if (part.type === 'data-citations' && Array.isArray(part.data?.citations)) {
      return part.data.citations
    }
  }
  return []
}

export function MessageList({ messages }: Props) {
  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-2 text-gray-400 text-sm">
        <p className="font-medium text-gray-500">Document Copilot</p>
        <p>Ask a question about the SEC filing corpus.</p>
        <p className="text-xs text-gray-300">e.g. "What was Apple's revenue in 2024?"</p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto space-y-4 p-4">
      {messages.map((message) => {
        const citations = extractCitations(message)
        return (
          <div
            key={message.id}
            className={`flex flex-col ${message.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div
              className={`max-w-2xl rounded-lg px-4 py-2 text-sm whitespace-pre-wrap ${
                message.role === 'user'
                  ? 'bg-violet-600 text-white'
                  : 'bg-gray-100 text-gray-900'
              }`}
            >
              {message.parts
                .filter((p): p is { type: 'text'; text: string } => p.type === 'text')
                .map((p, i) => (
                  <span key={i}>{p.text}</span>
                ))}
            </div>
            {citations.length > 0 && (
              <div className="max-w-2xl w-full mt-2 space-y-1">
                <p className="text-xs text-gray-400 font-medium px-1">Sources</p>
                {citations.map((c, i) => (
                  <CitationCard key={c.chunk_id} citation={c} index={i + 1} />
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
