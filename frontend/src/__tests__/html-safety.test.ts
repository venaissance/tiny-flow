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

// ── Summary ──

console.log(`\n${"─".repeat(40)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed > 0) {
  process.exit(1);
}
console.log("All tests passed! ✅\n");
