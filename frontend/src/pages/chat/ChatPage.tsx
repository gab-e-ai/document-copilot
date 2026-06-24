import { HttpChatTransport } from 'ai'
import { useChat } from '@ai-sdk/react'
import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { MessageInput } from '../../components/chat/MessageInput'
import { MessageList } from '../../components/chat/MessageList'
import { getAccessToken } from '../../lib/api'
import { env } from '../../lib/env'

const transport = new HttpChatTransport({
  api: `${env.apiBaseUrl}/chat/stream`,
  headers: async () => {
    const token = await getAccessToken()
    return { Authorization: `Bearer ${token}` }
  },
})

export function ChatPage() {
  const bottomRef = useRef<HTMLDivElement>(null)
  const [input, setInput] = useState('')

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
    void sendMessage({ text })
  }

  return (
    <div className="flex flex-col h-screen">
      <header className="border-b px-4 py-3">
        <h1 className="text-sm font-semibold">Document Copilot</h1>
      </header>
      <MessageList messages={messages} />
      {error && (
        <p role="alert" className="text-sm text-red-600 px-4 pb-2">
          {error.message}
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
