# JavaScript Safety Guidelines

These rules prevent runtime crashes and silent failures in the browser.

## 1. Always Null-Check DOM Elements

```javascript
// BAD - Crashes if element doesn't exist
document.getElementById('myElement').textContent = 'Hello';
document.getElementById('myElement').addEventListener('click', handler);
element.querySelector('.child').classList.add('active');

// GOOD - Safe with null checks
const el = document.getElementById('myElement');
if (el) {
    el.textContent = 'Hello';
}

// GOOD - Optional chaining (ES2020+)
document.getElementById('myElement')?.classList.add('active');

// GOOD - Early return pattern for functions
function updateElement() {
    const el = document.getElementById('myElement');
    if (!el) return;  // Guard clause

    el.textContent = 'Hello';
    el.classList.add('active');
}
```

### High-Risk Patterns to Avoid

| Pattern | Risk | Fix |
|---------|------|-----|
| `getElementById('x').method()` | Crashes if ID missing | Add null check |
| `querySelector('.x').method()` | Crashes if selector not found | Add null check |
| `el.querySelector('.x').querySelector('.y')` | Chained calls multiply risk | Check each step |
| `closest('.x').querySelector('.y')` | Both can return null | Check both |

---

## 2. Event Handler Parameter Rules

```javascript
// BAD - Relies on implicit global 'event' (doesn't exist in strict mode)
function handleClick() {
    event.preventDefault();  // 'event' is undefined!
    event.target.closest('.item');  // Crashes
}

// GOOD - Accept event as parameter
function handleClick(event) {
    event.preventDefault();
    event.target.closest('.item');
}

// BAD - Method loses 'this' context when used as listener
document.addEventListener('click', this.handleClick);

// GOOD - Bind the method or use arrow function
document.addEventListener('click', this.handleClick.bind(this));
document.addEventListener('click', (e) => this.handleClick(e));
```

### Event Listener Rules

1. Always accept `event` as the first parameter
2. Use `.bind(this)` or arrow functions when adding class methods as listeners
3. Remove listeners in cleanup (use `{ once: true }` for one-time handlers)

---

## 3. WebSocket Message Type Alignment (CRITICAL)

Server and client MUST handle the same message types.

```python
# Server (Python) - Document all message types in docstring
"""
Message Types (Server -> Client):
- {"type": "message", ...} - Chat response
- {"type": "error", ...} - Error occurred
- {"type": "typing", ...} - Typing indicator
"""
await websocket.send_json({"type": "message", ...})
```

```javascript
// Client (JavaScript) - Handle ALL server message types
handleMessage(data) {
    switch (data.type) {
        case 'message':  // Must match server's type value exactly
            this.displayMessage(data);
            break;
        case 'error':
            this.displayError(data.message);
            break;
        case 'typing':
            this.showTypingIndicator(data);
            break;
        default:
            console.warn('Unhandled message type:', data.type);
    }
}
```

### WebSocket Alignment Checklist

- [ ] Server docstring lists all message types
- [ ] Client switch statement handles all server types
- [ ] Type names match exactly (case-sensitive)
- [ ] Add `default` case to log unhandled types
- [ ] Test WebSocket communication after changes

---

## 4. Parallel API Calls with Promise.all()

When a page needs to load multiple pieces of data, run API calls in parallel:

```javascript
// BAD - Sequential (slow) - each call waits for the previous one
document.addEventListener('DOMContentLoaded', async function() {
    await loadUserData();      // 200ms
    await loadNotifications(); // 150ms
    await loadStats();         // 100ms
    // Total: 450ms
});

// GOOD - Parallel (fast) - all calls run simultaneously
document.addEventListener('DOMContentLoaded', function() {
    Promise.all([
        loadUserData(),
        loadNotifications(),
        loadStats()
    ]).catch(err => console.error('Error loading page data:', err));
    // Total: ~200ms (max of all three)
});
```

### Rules

1. **One DOMContentLoaded handler per page** - Don't scatter multiple handlers
2. **Use Promise.all for independent API calls** - If calls don't depend on each other
3. **Add error handling** - Always include `.catch()` to log errors
4. **Keep synchronous setup outside Promise.all** - Modal init, event listeners run immediately

### When to Use Sequential Calls

- When one API call needs data from a previous call's response
- When order of execution matters for UI state

---

## 5. AI Output Formatting (Lessons Learned)

When you need specific formatting in AI-generated content:

### Control the Source, Not the Output

```python
# BAD - vague instruction
"When mentioning pages, use markdown links"

# GOOD - exact template
"""Use EXACTLY this format:
- **[Clients](/clients)**: Add, search, or update client information
- **[Tasks](/tasks)**: Create, track, or manage tasks
"""
```

### Key Principles

1. **Specify exact format in prompts** - Don't post-process AI output with JavaScript
2. **Leverage existing parsers** - `marked.js` already renders markdown links
3. **Avoid complex DOM manipulation for text** - Walking text nodes breaks layout
4. **Regex pitfalls**: `regex.test()` advances `lastIndex` - causes bugs with subsequent `replace()`

---

## 6. Pre-Commit JavaScript Checklist

Before committing JavaScript changes:

- [ ] Search for `getElementById('` and verify null checks exist
- [ ] Search for `querySelector('` and verify null checks exist
- [ ] Search for `event.` and verify event parameter is declared
- [ ] If WebSocket: verify message types match between server/client
- [ ] Test in browser console for errors
- [ ] Hard refresh (Cmd+Shift+R / Ctrl+Shift+R) to bypass cache
