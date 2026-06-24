import type { UIMessage } from '@ai-sdk/react'

interface Props {
  messages: UIMessage[]
}

export function MessageList({ messages }: Props) {
  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
        Ask a question about the SEC filing corpus.
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto space-y-4 p-4">
      {messages.map((message) => (
        <div
          key={message.id}
          className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
        >
          <div
            className={`max-w-2xl rounded-lg px-4 py-2 text-sm whitespace-pre-wrap ${
              message.role === 'user'
                ? 'bg-violet-600 text-white'
                : 'bg-gray-100 text-gray-900'
            }`}
          >
            {message.parts
              .filter((p) => p.type === 'text')
              .map((p, i) => (
                <span key={i}>{(p as { type: 'text'; text: string }).text}</span>
              ))}
          </div>
        </div>
      ))}
    </div>
  )
}
