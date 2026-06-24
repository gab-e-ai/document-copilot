import type { ChangeEvent, FormEvent } from 'react'

interface Props {
  input: string
  onInputChange: (e: ChangeEvent<HTMLTextAreaElement>) => void
  onSubmit: (e: FormEvent<HTMLFormElement>) => void
  isStreaming: boolean
}

export function MessageInput({ input, onInputChange, onSubmit, isStreaming }: Props) {
  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      e.currentTarget.form?.requestSubmit()
    }
  }

  return (
    <form onSubmit={onSubmit} className="border-t p-4">
      <div className="flex gap-2 items-end">
        <textarea
          value={input}
          onChange={onInputChange}
          onKeyDown={handleKeyDown}
          placeholder="Ask about SEC filings… (Enter to send, Shift+Enter for newline)"
          disabled={isStreaming}
          rows={2}
          className="flex-1 resize-none rounded border px-3 py-2 text-sm disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-violet-500"
        />
        <button
          type="submit"
          disabled={isStreaming || !input.trim()}
          className="rounded bg-violet-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {isStreaming ? 'Streaming…' : 'Send'}
        </button>
      </div>
    </form>
  )
}
