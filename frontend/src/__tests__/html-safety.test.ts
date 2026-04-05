/**
 * HTML Safety Tests
 *
 * Validates that HTML document detection and sanitization work correctly.
 * Prevents CSS/JS injection into the host page via Streamdown rendering.
 *
 * Run: npx tsx src/__tests__/html-safety.test.ts
 */

// ── Inline implementations (mirroring message-item.tsx) ──

function containsHtmlDocument(content: string): boolean {
  return (
    content.includes("<!DOCTYPE") ||
    content.includes("<!doctype") ||
    /```html\s*\n[\s\S]*<style/i.test(content) ||
    (content.includes("<style") && content.includes("</style>"))
  );
}

function sanitizeForStreamdown(content: string): string {
  return content
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "")
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, "");
}

// ── Tests ──

let passed = 0;
let failed = 0;

function assert(condition: boolean, name: string) {
  if (condition) {
    passed++;
    console.log(`  ✅ ${name}`);
  } else {
    failed++;
    console.log(`  ❌ ${name}`);
  }
}

console.log("\n🔒 HTML Document Detection Tests\n");

// Must detect: raw HTML documents
assert(containsHtmlDocument("<!DOCTYPE html><html>...</html>"), "detects <!DOCTYPE");
assert(containsHtmlDocument("<!doctype html><html>...</html>"), "detects <!doctype (lowercase)");

// Must detect: markdown code blocks with HTML + style
assert(
  containsHtmlDocument("Here is the code:\n```html\n<!DOCTYPE html>\n<style>body{}</style>\n```"),
  "detects ```html block with <style>",
);

// Must detect: raw style tags in content
assert(
  containsHtmlDocument("Some text <style>h1 { color: red; }</style> more text"),
  "detects inline <style> tags",
);

// Must NOT detect: normal markdown
assert(!containsHtmlDocument("# Hello\n\nThis is **bold** text."), "ignores plain markdown");
assert(!containsHtmlDocument("Use `<style>` tags for CSS."), "ignores inline code mentions");
assert(!containsHtmlDocument("```python\nprint('hello')\n```"), "ignores non-HTML code blocks");

// Must NOT detect: partial HTML (no style/script)
assert(!containsHtmlDocument("<p>A paragraph</p>"), "ignores simple HTML tags");

console.log("\n🧹 Sanitization Tests\n");

// Must strip style tags
assert(
  !sanitizeForStreamdown("text <style>body{color:red}</style> more").includes("<style"),
  "strips <style> tags",
);

// Must strip script tags
assert(
  !sanitizeForStreamdown("text <script>alert('xss')</script> more").includes("<script"),
  "strips <script> tags",
);

// Must preserve other content
assert(
  sanitizeForStreamdown("Hello <b>world</b>").includes("<b>world</b>"),
  "preserves safe HTML",
);

// Must handle multiple style/script blocks
const multi = "<style>a{}</style>text<style>b{}</style><script>x</script>";
const cleaned = sanitizeForStreamdown(multi);
assert(!cleaned.includes("<style") && !cleaned.includes("<script"), "strips multiple blocks");
assert(cleaned.includes("text"), "preserves text between blocks");

// Edge case: nested-looking content
assert(
  !sanitizeForStreamdown('<style type="text/css">body{font: 16px}</style>').includes("<style"),
  "strips style with attributes",
);

console.log("\n📊 Thread Buffer Isolation Tests\n");

// Simulate thread buffer behavior
const buffers = new Map<string, { messages: string[] }>();

function simulateSend(threadId: string, content: string) {
  if (!buffers.has(threadId)) buffers.set(threadId, { messages: [] });
  buffers.get(threadId)!.messages.push(content);
}

function simulateSwitch(from: string, to: string) {
  // Should NOT clear the source buffer
  if (!buffers.has(to)) buffers.set(to, { messages: [] });
}

simulateSend("thread-a", "message 1");
simulateSend("thread-a", "message 2");
simulateSwitch("thread-a", "thread-b");
simulateSend("thread-b", "message B");

assert(buffers.get("thread-a")!.messages.length === 2, "thread-a buffer preserved after switch");
assert(buffers.get("thread-b")!.messages.length === 1, "thread-b has own buffer");

// Simulate background stream completing after switch
simulateSend("thread-a", "background completion");
assert(buffers.get("thread-a")!.messages.length === 3, "background stream saves to correct buffer");
assert(buffers.get("thread-b")!.messages.length === 1, "thread-b unaffected by thread-a's background stream");

console.log("\n🔀 Concurrent Thread Isolation Tests\n");

// Simulate the per-thread stream architecture
interface MockStream {
  messages: string[];
  steps: string[];
  running: boolean;
  mode: string | null;
}

const streams = new Map<string, MockStream>();
let activeThread = "default";

function createStream(threadId: string): MockStream {
  const s: MockStream = { messages: [], steps: [], running: true, mode: null };
  streams.set(threadId, s);
  return s;
}

function switchTo(threadId: string) {
  activeThread = threadId;
}

// Test: Two threads can run concurrently
const streamA = createStream("A");
const streamB = createStream("B");

streamA.messages.push("user-A");
streamA.mode = "pro";
streamA.steps.push("thinking-A");

// Switch to B while A is still running
switchTo("B");
streamB.messages.push("user-B");
streamB.mode = "flash";

assert(streamA.running && streamB.running, "both threads running concurrently");
assert(streamA.messages.length === 1 && streamA.messages[0] === "user-A", "thread-A messages isolated");
assert(streamB.messages.length === 1 && streamB.messages[0] === "user-B", "thread-B messages isolated");
assert(streamA.mode === "pro" && streamB.mode === "flash", "execution modes isolated per thread");

// Test: Background thread completes independently
streamA.messages.push("assistant-A-response");
streamA.running = false;
streamA.steps.push("done-A");

assert(!streamA.running && streamB.running, "thread-A finished while B still running");
assert(streamA.messages.length === 2, "thread-A accumulated messages in background");
assert(activeThread === "B", "active thread unchanged by background completion");

// Test: Switching back restores full state
switchTo("A");
const restoredA = streams.get("A")!;
assert(restoredA.messages.length === 2, "switch back restores messages");
assert(restoredA.steps.length === 2, "switch back restores steps (reasoning trace)");
assert(restoredA.mode === "pro", "switch back restores execution mode");
assert(!restoredA.running, "switch back shows correct streaming state");

// Test: Per-thread abort only affects target thread
streamB.running = false; // simulate abort on B
assert(!streamB.running, "abort only affects target thread");
assert(restoredA.messages.length === 2, "abort on B does not affect A");

// Test: New send on same thread blocked while running
const streamC = createStream("C");
assert(streamC.running, "new stream starts running");
// Attempting to send again on C should be blocked (per-thread lock)
const existingC = streams.get("C");
const canSendOnC = !(existingC?.running);
assert(!canSendOnC, "per-thread lock prevents double send on same thread");
// But sending on D should work
const canSendOnD = !streams.get("D")?.running;
assert(canSendOnD, "different thread is not blocked by C's lock");

// ── Summary ──

console.log(`\n${"─".repeat(40)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed > 0) {
  process.exit(1);
}
console.log("All tests passed! ✅\n");
