from pathlib import Path

SIDE = Path('app/src/main/java/com/aarishkhan/aarishai/AiSidecarController.kt')
s = SIDE.read_text(encoding='utf-8')

if 'AARISH_AI_COPY_BOTTOM_FIRST_V34' not in s:
    old = '''        fun seek(scrolls: Int) {
            if (!alive(run)) return
            val root = findRootForPackage(providerPackage(provider))
            if (root == null) { finish(null); return }
            val copy = findLearnedProviderControl(provider, root, AiTeachProfileStore.ROLE_COPY)
            if (copy != null) {
                val accepted = clickNode(copy)
                if (!accepted) { finish(null); return }
                handler.postDelayed({ pollClipboard(0) }, 100L)
                return
            }
            if (scrolls >= 4) { finish(null); return }
            val scrollable = findProviderScrollableForCopy(root)
            val moved = try { scrollable?.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD) == true } catch (_: Throwable) { false }
            if (!moved) { finish(null); return }
            handler.postDelayed({ seek(scrolls + 1) }, 260L)
        }
        seek(0)
'''
    new = '''        // AARISH_AI_COPY_BOTTOM_FIRST_V34
        // COPY repeats once per assistant message. A long newest reply can push its own action
        // row below the viewport while an older COPY is still visible. Do not click that older
        // control first: move the provider transcript toward its bounded end, then select the
        // bottom-most learned COPY. The request-id parser below still proves that copied text
        // belongs to this exact turn before any phone action can execute.
        fun seekLatest(scrolls: Int) {
            if (!alive(run)) return
            val root = findRootForPackage(providerPackage(provider))
            if (root == null) { finish(null); return }

            val scrollable = findProviderScrollableForCopy(root)
            if (scrolls < 5 && scrollable != null) {
                val moved = try {
                    scrollable.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD)
                } catch (_: Throwable) { false }
                if (moved) {
                    handler.postDelayed({ seekLatest(scrolls + 1) }, 240L)
                    return
                }
            }

            // We are at the bottom (or reached the strict scroll budget). The learned matcher
            // already applies AARISH_AI_COPY_LATEST_BIAS_V32, so repeated COPY controls resolve
            // to the lowest visible matching row rather than an old assistant message.
            val latestRoot = findRootForPackage(providerPackage(provider)) ?: root
            val copy = findLearnedProviderControl(
                provider,
                latestRoot,
                AiTeachProfileStore.ROLE_COPY
            )
            if (copy == null) { finish(null); return }
            val accepted = clickNode(copy)
            if (!accepted) { finish(null); return }
            handler.postDelayed({ pollClipboard(0) }, 100L)
        }
        seekLatest(0)
'''
    count = s.count(old)
    if count != 1:
        raise SystemExit(f'copy seek block: expected exactly one marker, found {count}')
    s = s.replace(old, new, 1)
    SIDE.write_text(s, encoding='utf-8')

text = SIDE.read_text(encoding='utf-8')
checks = {
    'bottom-first copy': 'AARISH_AI_COPY_BOTTOM_FIRST_V34' in text,
    'latest copy matcher': 'AARISH_AI_COPY_LATEST_BIAS_V32' in text,
    'request correlation parser': 'return parseCommand(text, requestId)' in text,
    'duplicate reattach guard': 'AARISH_AI_NO_DUPLICATE_REATTACH_V31' in text,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit('v3.4 invariant failure: ' + ', '.join(failed))

print('AARISH_UNIVERSAL_AI_TEACH_RELAY_V34_COPY_LATEST_READY')
