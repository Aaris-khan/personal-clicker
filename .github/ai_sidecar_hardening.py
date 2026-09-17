from pathlib import Path


def once(text: str, old: str, new: str, label: str) -> str:
    c = text.count(old)
    if c != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {c}")
    return text.replace(old, new, 1)

p = Path('app/src/main/java/com/aarishkhan/aarishai/AiSidecarController.kt')
s = p.read_text(encoding='utf-8')

if 'AARISH_AI_CLIPBOARD_PROOF_V2' not in s:
    old = '''                returnToTarget(run, lastTargetPackage) {\n                    if (!alive(run)) return@returnToTarget\n                    executeCommand(run, command, state) { executed, outcome ->\n'''
    new = '''                returnToTarget(run, lastTargetPackage) {\n                    if (!alive(run)) return@returnToTarget\n                    // AARISH_AI_CLIPBOARD_PROOF_V2: action se pehle clipboard baseline lo.\n                    val clipboardBefore = readClipboard()\n                    executeCommand(run, command, state) { executed, outcome ->\n'''
    s = once(s, old, new, 'clipboard baseline')
    old2 = '''                        verifyAfterAction(run, state, command) { verified, proof ->\n'''
    new2 = '''                        verifyAfterAction(run, state, command, clipboardBefore) { verified, proof ->\n'''
    s = once(s, old2, new2, 'verify call')
    old3 = '''    private fun verifyAfterAction(run: Int, before: ScreenState, command: AiCommand, callback: (Boolean, String) -> Unit) {\n        if (!alive(run)) return\n        val beforeClip = readClipboard()\n'''
    new3 = '''    private fun verifyAfterAction(\n        run: Int,\n        before: ScreenState,\n        command: AiCommand,\n        clipboardBefore: String,\n        callback: (Boolean, String) -> Unit\n    ) {\n        if (!alive(run)) return\n'''
    s = once(s, old3, new3, 'verify signature')
    s = once(s, '''            val clipChanged = readClipboard().let { it.isNotBlank() && it != beforeClip }\n''', '''            val clipChanged = readClipboard().let { it.isNotBlank() && it != clipboardBefore }\n''', 'clipboard compare')

if 'AARISH_AI_RETURN_TASK_V2' not in s:
    old = '''    private fun returnToTarget(run: Int, pkg: String, callback: () -> Unit) {\n        if (!alive(run)) return\n        if (pkg.isBlank() || pkg == service.packageName) {\n            callback(); return\n        }\n        try {\n            val launch = service.packageManager.getLaunchIntentForPackage(pkg)\n            if (launch != null) {\n                launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or Intent.FLAG_ACTIVITY_SINGLE_TOP)\n                service.startActivity(launch)\n            }\n        } catch (_: Throwable) {}\n        handler.postDelayed({ if (alive(run)) callback() }, 800L)\n    }\n'''
    new = '''    private fun returnToTarget(run: Int, pkg: String, callback: () -> Unit) {\n        if (!alive(run)) return\n        if (pkg.isBlank() || pkg == service.packageName) {\n            callback(); return\n        }\n\n        // AARISH_AI_RETURN_TASK_V2: existing task ko front lana first choice; launcher intent fallback.\n        var moved = false\n        try {\n            val am = service.getSystemService(Context.ACTIVITY_SERVICE) as? android.app.ActivityManager\n            @Suppress("DEPRECATION")\n            val tasks = am?.getRecentTasks(50, android.app.ActivityManager.RECENT_IGNORE_UNAVAILABLE).orEmpty()\n            val hit = tasks.firstOrNull { info ->\n                info.baseIntent?.component?.packageName == pkg || info.origActivity?.packageName == pkg\n            }\n            if (hit != null && am != null) {\n                try { am.moveTaskToFront(hit.id, 0); moved = true } catch (_: Throwable) {}\n            }\n        } catch (_: Throwable) {}\n\n        if (!moved) {\n            try {\n                val launch = service.packageManager.getLaunchIntentForPackage(pkg)\n                if (launch != null) {\n                    launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or Intent.FLAG_ACTIVITY_SINGLE_TOP)\n                    service.startActivity(launch)\n                }\n            } catch (_: Throwable) {}\n        }\n        handler.postDelayed({ if (alive(run)) callback() }, if (moved) 500L else 850L)\n    }\n'''
    s = once(s, old, new, 'return task')

if 'AARISH_AI_RICH_ACTIONS_V2' not in s:
    s = once(s,
        '''            appendLine("Allowed actions: TAP an element, SET_TEXT into an editable element, BACK, WAIT milliseconds, OPEN_APP by human app name, DONE, FAIL.")\n''',
        '''            appendLine("Allowed actions: TAP, LONG_TAP, SET_TEXT, SCROLL (UP/DOWN), BACK, HOME, WAIT milliseconds, OPEN_APP by human app name, DONE, FAIL.")\n            appendLine("For SCROLL use an element key when a scrollable container is listed; otherwise leave element empty and put UP or DOWN in the final field.")\n''',
        'prompt actions')
    s = once(s,
        '''        if (action !in setOf("TAP", "SET_TEXT", "BACK", "WAIT", "OPEN_APP", "DONE", "FAIL")) return null\n''',
        '''        if (action !in setOf("TAP", "LONG_TAP", "SET_TEXT", "SCROLL", "BACK", "HOME", "WAIT", "OPEN_APP", "DONE", "FAIL")) return null\n''',
        'parse actions')

    old_exec = '''        when (command.action) {\n            "BACK" -> callback(service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK), "Back")\n            "WAIT" -> {\n'''
    new_exec = '''        when (command.action) {\n            // AARISH_AI_RICH_ACTIONS_V2\n            "BACK" -> callback(service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK), "Back")\n            "HOME" -> callback(service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME), "Home")\n            "WAIT" -> {\n'''
    s = once(s, old_exec, new_exec, 'home action')

    s = once(s,
        '''            "TAP", "SET_TEXT" -> {\n''',
        '''            "TAP", "LONG_TAP", "SET_TEXT" -> {\n''',
        'tap action set')
    old_tail = '''                if (command.action == "SET_TEXT") {\n                    val args = Bundle().apply {\n                        putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, command.payload.take(12000))\n                    }\n                    val ok = try { live.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args) } catch (_: Throwable) { false }\n                    callback(ok, "Set text ${saved.key}")\n                } else {\n                    callback(clickNode(live), "Tapped ${saved.key}")\n                }\n            }\n            else -> callback(false, "Unsupported action")\n'''
    new_tail = '''                if (command.action == "SET_TEXT") {\n                    val args = Bundle().apply {\n                        putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, command.payload.take(12000))\n                    }\n                    val ok = try { live.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args) } catch (_: Throwable) { false }\n                    callback(ok, "Set text ${saved.key}")\n                } else if (command.action == "LONG_TAP") {\n                    callback(longClickNode(live), "Long tapped ${saved.key}")\n                } else {\n                    callback(clickNode(live), "Tapped ${saved.key}")\n                }\n            }\n            "SCROLL" -> {\n                val direction = command.payload.trim().uppercase(Locale.US)\n                val saved = state.elements.firstOrNull { it.key.equals(command.elementKey, true) }\n                val live = saved?.let { findBestLiveMatch(it) } ?: findScrollableNode()\n                if (live == null) {\n                    callback(false, "Scrollable container not found")\n                } else {\n                    val action = if (direction.contains("UP") || direction.contains("BACK"))\n                        AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD\n                    else AccessibilityNodeInfo.ACTION_SCROLL_FORWARD\n                    val ok = try { live.performAction(action) } catch (_: Throwable) { false }\n                    callback(ok, "Scrolled ${if (action == AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD) "UP" else "DOWN"}")\n                }\n            }\n            else -> callback(false, "Unsupported action")\n'''
    s = once(s, old_tail, new_tail, 'rich execute')

    insert_anchor = '''    private fun clickNode(node: AccessibilityNodeInfo): Boolean {\n'''
    helpers = '''    private fun findScrollableNode(): AccessibilityNodeInfo? {\n        val root = findBestTargetRoot() ?: return null\n        var best: AccessibilityNodeInfo? = null\n        var bestArea = -1\n        walk(root, 4500) { n ->\n            val scrollable = try { n.isScrollable && n.isVisibleToUser && n.isEnabled } catch (_: Throwable) { false }\n            if (!scrollable) return@walk\n            val b = Rect(); try { n.getBoundsInScreen(b) } catch (_: Throwable) {}\n            val area = b.width().coerceAtLeast(0) * b.height().coerceAtLeast(0)\n            if (area > bestArea) { bestArea = area; best = n }\n        }\n        return best\n    }\n\n    private fun longClickNode(node: AccessibilityNodeInfo): Boolean {\n        try { if (node.performAction(AccessibilityNodeInfo.ACTION_LONG_CLICK)) return true } catch (_: Throwable) {}\n        val b = Rect(); try { node.getBoundsInScreen(b) } catch (_: Throwable) { return false }\n        if (b.isEmpty || Build.VERSION.SDK_INT < 24) return false\n        val path = Path().apply { moveTo(b.exactCenterX(), b.exactCenterY()) }\n        return try {\n            val gesture = GestureDescription.Builder()\n                .addStroke(GestureDescription.StrokeDescription(path, 0L, 650L))\n                .build()\n            service.dispatchGesture(gesture, null, null)\n        } catch (_: Throwable) { false }\n    }\n\n'''
    s = once(s, insert_anchor, helpers + insert_anchor, 'scroll long helpers')

if 'AARISH_AI_GENERATION_DETECT_V2' not in s:
    old = '''            if (label.contains("stop generating") || label.contains("stop response") || label.contains("cancel response") || label.contains("interrupt response")) {\n                found = true\n            }\n'''
    new = '''            val exact = label.trim()\n            val clickable = try { n.isClickable } catch (_: Throwable) { false }\n            // AARISH_AI_GENERATION_DETECT_V2\n            if (label.contains("stop generating") || label.contains("stop response") || label.contains("cancel response") ||\n                label.contains("interrupt response") || (clickable && exact == "stop")) {\n                found = true\n            }\n'''
    s = once(s, old, new, 'generation detect')

if 'AARISH_AI_SEND_GUARD_V2' not in s:
    old = '''            if (label.contains("voice") || label.contains("mic") || label.contains("attach")) score -= 260\n'''
    new = '''            if (label.contains("voice") || label.contains("mic") || label.contains("attach")) score -= 260\n            // AARISH_AI_SEND_GUARD_V2: unrelated send/share controls ko composer Send se neeche rakho.\n            if (label.contains("feedback") || label.contains("share") || label.contains("send to")) score -= 420\n'''
    s = once(s, old, new, 'send guard')

p.write_text(s, encoding='utf-8')

auto_path = Path('app/src/main/java/com/aarishkhan/aarishai/AutoActionService.kt')
auto = auto_path.read_text(encoding='utf-8')
if 'AARISH_AI_CANCEL_WITH_PLAYBACK_V2' not in auto:
    anchor = '''    private fun stopPlaybackInternal() {\n'''
    replacement = '''    private fun stopPlaybackInternal() {\n        // AARISH_AI_CANCEL_WITH_PLAYBACK_V2: STOP means rescue/mission callbacks must not continue stale work.\n        try { if (aiSidecarController.isRunning()) aiSidecarController.stop("stopped") } catch (_: Throwable) {}\n'''
    auto = once(auto, anchor, replacement, 'stop playback AI cancel')
auto_path.write_text(auto, encoding='utf-8')

print('AI sidecar hardening applied.')
