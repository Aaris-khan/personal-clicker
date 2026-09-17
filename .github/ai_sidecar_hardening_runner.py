from pathlib import Path

patcher = Path('.github/ai_sidecar_hardening.py')
text = patcher.read_text(encoding='utf-8')

old_anchor = "anchor = '''    private fun stopPlaybackInternal() {\\n'''"
new_anchor = "anchor = '''private fun stopPlaybackInternal(showToast: Boolean = true) {\\n'''"
old_repl = "replacement = '''    private fun stopPlaybackInternal() {\\n"
new_repl = "replacement = '''private fun stopPlaybackInternal(showToast: Boolean = true) {\\n"

if old_anchor in text:
    text = text.replace(old_anchor, new_anchor, 1)
if old_repl in text:
    text = text.replace(old_repl, new_repl, 1)

if new_anchor not in text or new_repl not in text:
    raise SystemExit('Unable to normalize stopPlaybackInternal patcher anchor')

# Execute the normalized patcher in-memory. The repository copy stays unchanged.
code = compile(text, str(patcher), 'exec')
exec(code, {'__name__': '__main__', '__file__': str(patcher)})
