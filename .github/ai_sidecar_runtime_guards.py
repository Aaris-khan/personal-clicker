from pathlib import Path

p = Path('app/src/main/java/com/aarishkhan/aarishai/AiSidecarController.kt')
s = p.read_text(encoding='utf-8')


def once(old: str, new: str, label: str) -> None:
    global s
    count = s.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 occurrence, found {count}')
    s = s.replace(old, new, 1)


if 'AARISH_AI_RESCUE_STOP_RELEASE_V3' not in s:
    once(
        '''    fun stop(reason: String = "stopped") {
        generation.incrementAndGet()
        missionRunning = false
        waitingForAi = false
        rescueMode = false
        rescueCallback = null
        handler.removeCallbacksAndMessages(null)
        if (reason != "restart") toast("AI agent $reason")
    }
''',
        '''    fun stop(reason: String = "stopped") {
        // AARISH_AI_RESCUE_STOP_RELEASE_V3: stopping rescue must release playback waiter too.
        val pendingRescue = if (rescueMode) rescueCallback else null
        generation.incrementAndGet()
        missionRunning = false
        waitingForAi = false
        rescueMode = false
        rescueCallback = null
        handler.removeCallbacksAndMessages(null)
        try { pendingRescue?.invoke(false) } catch (_: Throwable) {}
        if (reason != "restart") toast("AI agent $reason")
    }
''',
        'rescue stop release'
    )

if 'AARISH_AI_TARGET_ROOT_RANKING_V3' not in s:
    once(
        '''    private fun findBestTargetRoot(): AccessibilityNodeInfo? {
        val forbidden = setOf(service.packageName, Provider.CHATGPT.packageName, Provider.GEMINI.packageName)
        return try {
            service.windows.asSequence()
                .mapNotNull { it.root }
                .firstOrNull { root ->
                    val pkg = root.packageName?.toString().orEmpty()
                    pkg.isNotBlank() && pkg !in forbidden && !pkg.contains("inputmethod", true) && !pkg.contains("keyboard", true)
                }
                ?: service.rootInActiveWindow?.takeIf {
                    val pkg = it.packageName?.toString().orEmpty()
                    pkg.isNotBlank() && pkg !in forbidden
                }
        } catch (_: Throwable) { null }
    }
''',
        '''    private fun findBestTargetRoot(): AccessibilityNodeInfo? {
        // AARISH_AI_TARGET_ROOT_RANKING_V3: active/focused app windows beat incidental overlays.
        val forbidden = setOf(service.packageName, Provider.CHATGPT.packageName, Provider.GEMINI.packageName)
        return try {
            val screenArea = (service.resources.displayMetrics.widthPixels.toLong().coerceAtLeast(1L) *
                service.resources.displayMetrics.heightPixels.toLong().coerceAtLeast(1L)).coerceAtLeast(1L)
            var best: AccessibilityNodeInfo? = null
            var bestScore = Int.MIN_VALUE

            for (window in service.windows) {
                val root = window.root ?: continue
                val pkg = root.packageName?.toString().orEmpty()
                if (pkg.isBlank() || pkg in forbidden || pkg.contains("inputmethod", true) || pkg.contains("keyboard", true)) continue

                val b = Rect()
                try { root.getBoundsInScreen(b) } catch (_: Throwable) {}
                if (b.width() <= 0 || b.height() <= 0) continue
                val area = b.width().toLong() * b.height().toLong()
                val areaRatio = (area.toDouble() / screenArea.toDouble()).coerceIn(0.0, 1.0)

                var score = (areaRatio * 3000.0).toInt()
                if (window.isActive) score += 10000
                if (window.isFocused) score += 12000
                if (window.type == android.view.accessibility.AccessibilityWindowInfo.TYPE_APPLICATION) score += 2500
                score += window.layer.coerceIn(-100, 100) * 20
                if (pkg == "com.android.systemui" && areaRatio < 0.55) score -= 9000

                if (score > bestScore) {
                    bestScore = score
                    best = root
                }
            }

            best ?: service.rootInActiveWindow?.takeIf {
                val pkg = it.packageName?.toString().orEmpty()
                pkg.isNotBlank() && pkg !in forbidden && !pkg.contains("inputmethod", true) && !pkg.contains("keyboard", true)
            }
        } catch (_: Throwable) { null }
    }
''',
        'target root ranking'
    )

if 'AARISH_AI_DONE_EVIDENCE_V3' not in s:
    once(
        '''            appendLine("Reply with ONE single machine line and no prose. Construct it as: word AARIS, two colons, request identifier, two colons, action name, two colons, element key or empty, two colons, payload/expected text.")
''',
        '''            // AARISH_AI_DONE_EVIDENCE_V3
            appendLine("Use DONE only when the CURRENT visible screen/state provides evidence that the user's goal is complete; never mark DONE from assumption or an earlier screen.")
            appendLine("Reply with ONE single machine line and no prose. Construct it as: word AARIS, two colons, request identifier, two colons, action name, two colons, element key or empty, two colons, payload/expected text.")
''',
        'done evidence'
    )

if 'AARISH_AI_NULL_RESPONSE_RETURN_V3' not in s:
    once(
        '''                if (command == null) {
                    failTurn(run, "AI response parse/timeout")
                    return@askPhysicalAi
                }
''',
        '''                if (command == null) {
                    // AARISH_AI_NULL_RESPONSE_RETURN_V3: timeout/parse failure must not strand provider UI.
                    returnToTarget(run, lastTargetPackage) {
                        if (alive(run)) failTurn(run, "AI response parse/timeout")
                    }
                    return@askPhysicalAi
                }
''',
        'null response return'
    )

p.write_text(s, encoding='utf-8')
print('AI sidecar runtime guards applied.')
