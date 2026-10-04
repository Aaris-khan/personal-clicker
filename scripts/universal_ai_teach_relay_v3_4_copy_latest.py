from pathlib import Path

SIDE = Path('app/src/main/java/com/aarishkhan/aarishai/AiSidecarController.kt')
s = SIDE.read_text(encoding='utf-8')

# A normalized fallback point is safe only when teaching proved there was no useful
# Accessibility SEND node at all. Semantic SEND profiles must never silently degrade
# into blind coordinate replay after a future UI redesign.
if 'AARISH_AI_SEND_XY_SYNTHETIC_ONLY_V35' not in s:
    old_point = '''    // AARISH_AI_LEARNED_POINT_V32
    private fun learnedProviderPoint(provider: Provider, role: String): Pair<Float, Float>? {
        val fp = AiTeachProfileStore.role(service, providerPackage(provider), role) ?: return null
        if (fp.xPercent.isNaN() || fp.yPercent.isNaN() ||
            fp.xPercent.isInfinite() || fp.yPercent.isInfinite()
        ) return null
        return fp.xPercent.coerceIn(0f, 1f) to fp.yPercent.coerceIn(0f, 1f)
    }
'''
    new_point = '''    // AARISH_AI_LEARNED_POINT_V32
    private fun learnedProviderPoint(provider: Provider, role: String): Pair<Float, Float>? {
        if (!role.equals(AiTeachProfileStore.ROLE_SEND, ignoreCase = true)) return null
        val fp = AiTeachProfileStore.role(service, providerPackage(provider), role) ?: return null

        // AARISH_AI_SEND_XY_SYNTHETIC_ONLY_V35
        // Coordinate replay is allowed only for a SEND that was explicitly learned because
        // Accessibility exposed no usable node. If a normal semantic fingerprint later stops
        // matching after an app update, fail closed/re-teach instead of tapping its stale point.
        val explicitXyFallback =
            fp.className.equals("TAUGHT_SEND_XY", ignoreCase = true) ||
                fp.treePath.equals("TAUGHT_SEND_XY", ignoreCase = true) ||
                fp.roleFlags.split('|').any { it.equals("xy_fallback", ignoreCase = true) }
        if (!explicitXyFallback) return null

        if (fp.xPercent.isNaN() || fp.yPercent.isNaN() ||
            fp.xPercent.isInfinite() || fp.yPercent.isInfinite()
        ) return null
        return fp.xPercent.coerceIn(0f, 1f) to fp.yPercent.coerceIn(0f, 1f)
    }
'''
    count = s.count(old_point)
    if count != 1:
        raise SystemExit(f'learned point block: expected exactly one marker, found {count}')
    s = s.replace(old_point, new_point, 1)

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
    'synthetic-only send point': 'AARISH_AI_SEND_XY_SYNTHETIC_ONLY_V35' in text,
    'bottom-first copy': 'AARISH_AI_COPY_BOTTOM_FIRST_V34' in text,
    'latest copy matcher': 'AARISH_AI_COPY_LATEST_BIAS_V32' in text,
    'request correlation parser': 'return parseCommand(text, requestId)' in text,
    'duplicate reattach guard': 'AARISH_AI_NO_DUPLICATE_REATTACH_V31' in text,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit('v3.4/v3.5 invariant failure: ' + ', '.join(failed))

print('AARISH_UNIVERSAL_AI_TEACH_RELAY_V35_SAFE_COPY_AND_SEND_READY')
