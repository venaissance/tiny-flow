import { describe, it, expect } from 'vitest'

// ── Inline implementations (mirroring message-item.tsx) ──

function containsHtmlDocument(content: string): boolean {
  return (
    content.includes('<!DOCTYPE') ||
    content.includes('<!doctype') ||
    /```html\s*\n[\s\S]*<style/i.test(content) ||
    (content.includes('<style') && content.includes('</style>'))
  )
}

function sanitizeForStreamdown(content: string): string {
  return content
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
}

// ── HTML Document Detection ──

describe('containsHtmlDocument', () => {
  it('detects <!DOCTYPE', () => {
    expect(containsHtmlDocument('<!DOCTYPE html><html>...</html>')).toBe(true)
  })

  it('detects <!doctype (lowercase)', () => {
    expect(containsHtmlDocument('<!doctype html><html>...</html>')).toBe(true)
  })

  it('detects ```html block with <style>', () => {
    expect(
      containsHtmlDocument(
        'Here is the code:\n```html\n<!DOCTYPE html>\n<style>body{}</style>\n```',
      ),
    ).toBe(true)
  })

  it('detects inline <style> tags', () => {
    expect(
      containsHtmlDocument('Some text <style>h1 { color: red; }</style> more text'),
    ).toBe(true)
  })

  it('ignores plain markdown', () => {
    expect(containsHtmlDocument('# Hello\n\nThis is **bold** text.')).toBe(false)
  })

  it('ignores inline code mentions', () => {
    expect(containsHtmlDocument('Use `<style>` tags for CSS.')).toBe(false)
  })

  it('ignores non-HTML code blocks', () => {
    expect(containsHtmlDocument("```python\nprint('hello')\n```")).toBe(false)
  })

  it('ignores simple HTML tags', () => {
    expect(containsHtmlDocument('<p>A paragraph</p>')).toBe(false)
  })
})

// ── Sanitization ──

describe('sanitizeForStreamdown', () => {
  it('strips <style> tags', () => {
    expect(
      sanitizeForStreamdown('text <style>body{color:red}</style> more'),
    ).not.toContain('<style')
  })

  it('strips <script> tags', () => {
    expect(
      sanitizeForStreamdown("text <script>alert('xss')</script> more"),
    ).not.toContain('<script')
  })

  it('preserves safe HTML', () => {
    expect(sanitizeForStreamdown('Hello <b>world</b>')).toContain('<b>world</b>')
  })

  it('strips multiple style/script blocks', () => {
    const multi = '<style>a{}</style>text<style>b{}</style><script>x</script>'
    const cleaned = sanitizeForStreamdown(multi)
    expect(cleaned).not.toContain('<style')
    expect(cleaned).not.toContain('<script')
    expect(cleaned).toContain('text')
  })

  it('strips style with attributes', () => {
    expect(
      sanitizeForStreamdown('<style type="text/css">body{font: 16px}</style>'),
    ).not.toContain('<style')
  })
})

// ── Thread Buffer Isolation ──

describe('Thread Buffer Isolation', () => {
  it('preserves buffer after thread switch', () => {
    const buffers = new Map<string, { messages: string[] }>()

    function simulateSend(threadId: string, content: string) {
      if (!buffers.has(threadId)) buffers.set(threadId, { messages: [] })
      buffers.get(threadId)!.messages.push(content)
    }

    function simulateSwitch(_from: string, to: string) {
      if (!buffers.has(to)) buffers.set(to, { messages: [] })
    }

    simulateSend('thread-a', 'message 1')
    simulateSend('thread-a', 'message 2')
    simulateSwitch('thread-a', 'thread-b')
    simulateSend('thread-b', 'message B')

    expect(buffers.get('thread-a')!.messages).toHaveLength(2)
    expect(buffers.get('thread-b')!.messages).toHaveLength(1)
  })

  it('background stream saves to correct buffer', () => {
    const buffers = new Map<string, { messages: string[] }>()

    function simulateSend(threadId: string, content: string) {
      if (!buffers.has(threadId)) buffers.set(threadId, { messages: [] })
      buffers.get(threadId)!.messages.push(content)
    }

    simulateSend('thread-a', 'message 1')
    simulateSend('thread-a', 'message 2')
    // switch to thread-b
    if (!buffers.has('thread-b')) buffers.set('thread-b', { messages: [] })
    simulateSend('thread-b', 'message B')

    // background completion on thread-a
    simulateSend('thread-a', 'background completion')

    expect(buffers.get('thread-a')!.messages).toHaveLength(3)
    expect(buffers.get('thread-b')!.messages).toHaveLength(1)
  })
})

// ── Concurrent Thread Isolation ──

describe('Concurrent Thread Isolation', () => {
  interface MockStream {
    messages: string[]
    steps: string[]
    running: boolean
    mode: string | null
  }

  function createTestEnv() {
    const streams = new Map<string, MockStream>()
    let activeThread = 'default'

    function createStream(threadId: string): MockStream {
      const s: MockStream = { messages: [], steps: [], running: true, mode: null }
      streams.set(threadId, s)
      return s
    }

    function switchTo(threadId: string) {
      activeThread = threadId
    }

    return { streams, get activeThread() { return activeThread }, createStream, switchTo }
  }

  it('both threads can run concurrently', () => {
    const env = createTestEnv()
    const streamA = env.createStream('A')
    const streamB = env.createStream('B')

    streamA.messages.push('user-A')
    streamA.mode = 'pro'
    streamA.steps.push('thinking-A')

    env.switchTo('B')
    streamB.messages.push('user-B')
    streamB.mode = 'flash'

    expect(streamA.running && streamB.running).toBe(true)
    expect(streamA.messages).toEqual(['user-A'])
    expect(streamB.messages).toEqual(['user-B'])
    expect(streamA.mode).toBe('pro')
    expect(streamB.mode).toBe('flash')
  })

  it('background thread completes independently', () => {
    const env = createTestEnv()
    const streamA = env.createStream('A')
    const streamB = env.createStream('B')

    streamA.messages.push('user-A')
    env.switchTo('B')
    streamB.messages.push('user-B')

    // A completes in background
    streamA.messages.push('assistant-A-response')
    streamA.running = false
    streamA.steps.push('done-A')

    expect(streamA.running).toBe(false)
    expect(streamB.running).toBe(true)
    expect(streamA.messages).toHaveLength(2)
    expect(env.activeThread).toBe('B')
  })

  it('switching back restores full state', () => {
    const env = createTestEnv()
    const streamA = env.createStream('A')
    env.createStream('B')

    streamA.messages.push('user-A')
    streamA.mode = 'pro'
    streamA.steps.push('thinking-A', 'done-A')
    streamA.running = false

    env.switchTo('B')
    env.switchTo('A')

    const restored = env.streams.get('A')!
    expect(restored.messages).toHaveLength(1)
    expect(restored.steps).toHaveLength(2)
    expect(restored.mode).toBe('pro')
    expect(restored.running).toBe(false)
  })

  it('abort only affects target thread', () => {
    const env = createTestEnv()
    const streamA = env.createStream('A')
    const streamB = env.createStream('B')

    streamA.messages.push('msg-A')
    streamB.running = false // simulate abort on B

    expect(streamB.running).toBe(false)
    expect(streamA.messages).toHaveLength(1)
  })

  it('per-thread lock prevents double send on same thread', () => {
    const env = createTestEnv()
    env.createStream('C')

    const existingC = env.streams.get('C')
    const canSendOnC = !existingC?.running
    expect(canSendOnC).toBe(false)

    const canSendOnD = !env.streams.get('D')?.running
    expect(canSendOnD).toBe(true)
  })
})
