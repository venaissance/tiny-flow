import { describe, it, expect, vi } from 'vitest'
import { parseSSELines } from '@/hooks/use-chat'
import type { SSEEventType } from '@/lib/types'

describe('parseSSELines', () => {
  function createState(): { value: SSEEventType } {
    return { value: 'content' }
  }

  it('parses a basic content event', () => {
    const cb = vi.fn()
    const state = createState()

    parseSSELines(['data: {"content":"hello"}'], state, cb)

    expect(cb).toHaveBeenCalledOnce()
    expect(cb).toHaveBeenCalledWith('content', { content: 'hello' })
  })

  it('switches event type via "event:" line', () => {
    const cb = vi.fn()
    const state = createState()

    parseSSELines(['event: thinking', 'data: {"content":"deep thought"}'], state, cb)

    expect(cb).toHaveBeenCalledOnce()
    expect(cb).toHaveBeenCalledWith('thinking', { content: 'deep thought' })
  })

  it('resets event type to "content" after processing a data line', () => {
    const cb = vi.fn()
    const state = createState()

    parseSSELines(
      ['event: thinking', 'data: {"content":"thought"}', 'data: {"content":"next"}'],
      state,
      cb,
    )

    expect(cb).toHaveBeenCalledTimes(2)
    expect(cb).toHaveBeenNthCalledWith(1, 'thinking', { content: 'thought' })
    expect(cb).toHaveBeenNthCalledWith(2, 'content', { content: 'next' })
  })

  it('skips empty lines', () => {
    const cb = vi.fn()
    parseSSELines(['', '  ', '\t'], createState(), cb)
    expect(cb).not.toHaveBeenCalled()
  })

  it('skips comment lines starting with ":"', () => {
    const cb = vi.fn()
    parseSSELines([': keep-alive', ':comment'], createState(), cb)
    expect(cb).not.toHaveBeenCalled()
  })

  it('skips "id:" lines', () => {
    const cb = vi.fn()
    parseSSELines(['id: 12345'], createState(), cb)
    expect(cb).not.toHaveBeenCalled()
  })

  it('silently ignores invalid JSON in data lines', () => {
    const cb = vi.fn()
    parseSSELines(['data: {not valid json}'], createState(), cb)
    expect(cb).not.toHaveBeenCalled()
  })

  it('handles multiple events in one chunk', () => {
    const cb = vi.fn()
    const lines = [
      'event: thinking',
      'data: {"content":"a"}',
      'event: tool_call',
      'data: {"name":"search","query":"test"}',
      'data: {"content":"b"}',
    ]

    parseSSELines(lines, createState(), cb)

    expect(cb).toHaveBeenCalledTimes(3)
    expect(cb).toHaveBeenNthCalledWith(1, 'thinking', { content: 'a' })
    expect(cb).toHaveBeenNthCalledWith(2, 'tool_call', { name: 'search', query: 'test' })
    expect(cb).toHaveBeenNthCalledWith(3, 'content', { content: 'b' })
  })

  it('supports all SSE event types', () => {
    const eventTypes: SSEEventType[] = [
      'thinking',
      'content',
      'tool_call',
      'tool_result',
      'mode_selected',
      'todo_update',
      'done',
      'error',
    ]

    for (const eventType of eventTypes) {
      const cb = vi.fn()
      const state = createState()
      parseSSELines([`event: ${eventType}`, 'data: {"ok":true}'], state, cb)
      expect(cb).toHaveBeenCalledWith(eventType, { ok: true })
    }
  })

  it('preserves currentEvent state across calls', () => {
    const cb = vi.fn()
    const state = createState()

    // First call sets event type but no data line
    parseSSELines(['event: error'], state, cb)
    expect(cb).not.toHaveBeenCalled()
    expect(state.value).toBe('error')

    // Second call picks up the event type
    parseSSELines(['data: {"error":"timeout"}'], state, cb)
    expect(cb).toHaveBeenCalledWith('error', { error: 'timeout' })

    // After data, resets to content
    expect(state.value).toBe('content')
  })
})
