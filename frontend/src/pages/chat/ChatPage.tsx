import { useChat } from '@ai-sdk/react'
import { DefaultChatTransport } from 'ai'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { MessageInput } from '../../components/chat/MessageInput'
import { MessageList } from '../../components/chat/MessageList'
import { getAccessToken } from '../../lib/api'
import { env } from '../../lib/env'

export function ChatPage() {
  const bottomRef = useRef<HTMLDivElement>(null)
  const [input, setInput] = useState('')

  // AI SDK v6 routes requests through a transport; the top-level `api`/`fetch`
  // options are ignored. DefaultChatTransport lets us point at the backend and
  // inject the Supabase bearer token per request.
  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: `${env.apiBaseUrl}/chat/stream`,
        fetch: async (input, init) => {
          const token = await getAccessToken()
          return fetch(input, {
            ...init,
            headers: { ...init?.headers, Authorization: `Bearer ${token}` },
          })
        },
      }),
    [],
  )

  const { messages, sendMessage, status, error } = useChat({ transport })

  const isStreaming = status === 'streaming' || status === 'submitted'

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function handleInputChange(e: ChangeEvent<HTMLTextAreaElement>) {
    setInput(e.target.value)
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const text = input.trim()
    if (!text || isStreaming) return
    setInput('')
    sendMessage({ text }).catch(() => {})
  }

  function errorMessage(err: Error): string {
    const msg = err.message ?? ''
    if (msg.includes('401') || msg.includes('403')) return 'Session expired — please sign in again.'
    if (msg.includes('502') || msg.includes('500')) return 'The assistant is temporarily unavailable. Please try again.'
    return 'Something went wrong. Please try again.'
  }

  return (
    <div className="flex flex-col h-screen">
      <header className="border-b px-4 py-3">
        <h1 className="text-sm font-semibold">Document Copilot</h1>
      </header>
      <MessageList messages={messages} />
      {error && (
        <p role="alert" className="text-sm text-red-600 px-4 pb-2 text-center">
          {errorMessage(error)}
        </p>
      )}
      <div ref={bottomRef} />
      <MessageInput
        input={input}
        onInputChange={handleInputChange}
        onSubmit={handleSubmit}
        isStreaming={isStreaming}
      />
    </div>
  )
}
