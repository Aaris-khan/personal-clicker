from pathlib import Path
import re

sidecar_path = Path("app/src/main/java/com/aarishkhan/aarishai/AiSidecarController.kt")
auto_path = Path("app/src/main/java/com/aarishkhan/aarishai/AutoActionService.kt")
sidecar = sidecar_path.read_text()
auto = auto_path.read_text()


def exact(text: str, old: str, new: str, label: str, expected: int = 1) -> str:
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"{label}: expected {expected} exact match(es), found {count}")
    return text.replace(old, new)


def sub(text: str, pattern: str, replacement: str, label: str, flags: int = 0) -> str:
    out, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 regex match, found {count}")
    return out


# --- AiSidecarController: make replay rescue a bounded, multi-turn mini mission. ---
sidecar = exact(
    sidecar,
    '    private var rescueMode = false\n    private val actionHistory = java.util.ArrayDeque<String>()',
    '    private var rescueMode = false\n    private var rescueExpectedAction = ""\n    private val actionHistory = java.util.ArrayDeque<String>()',
    "rescue expected action field",
)

sidecar = exact(
    sidecar,
    '    fun isRunning(): Boolean = missionRunning || waitingForAi\n\n    fun startMission',
    '''    fun isRunning(): Boolean = missionRunning || waitingForAi

    private fun inferRecordedAction(gesture: RecordedGesture): String {
        val points = gesture.points
            .filter { !it.x.isNaN() && !it.x.isInfinite() && !it.y.isNaN() && !it.y.isInfinite() }
            .sortedBy { it.t.coerceAtLeast(0L) }
        if (points.isEmpty()) return "TAP"

        val first = points.first()
        var maxDx = 0f
        var maxDy = 0f
        for (i in 1 until points.size) {
            maxDx = kotlin.math.max(maxDx, abs(points[i].x - first.x))
            maxDy = kotlin.math.max(maxDy, abs(points[i].y - first.y))
        }
        val slop = kotlin.math.max(10f, 6f * service.resources.displayMetrics.density)
        if (maxDx > slop || maxDy > slop) return "SCROLL"

        val duration = points.maxOfOrNull { it.t.coerceAtLeast(0L) } ?: 0L
        return if (duration >= 450L) "LONG_TAP" else "TAP"
    }

    fun startMission''',
    "recorded action inference",
)

sidecar = sub(
    sidecar,
    r'''(fun startMission\(goal: String, provider: String = "AUTO"\): Boolean \{.*?        rescueMode = false\n)''',
    r'''\1        rescueExpectedAction = ""\n''',
    "normal mission rescue reset",
    re.S,
)

sidecar = exact(
    sidecar,
    '''        val target = listOfNotNull(
            gesture.targetText,
            gesture.targetDesc,
            gesture.targetId,
            gesture.targetClass,
            gesture.targetContextText
        ).filter { it.isNotBlank() }.joinToString(" | ").take(1800)

        missionGoal = buildString {''',
    '''        val target = listOfNotNull(
            gesture.targetText,
            gesture.targetDesc,
            gesture.targetId,
            gesture.targetClass,
            gesture.targetContextText
        ).filter { it.isNotBlank() }.joinToString(" | ").take(1800)
        rescueExpectedAction = inferRecordedAction(gesture)

        missionGoal = buildString {''',
    "rescue action classification",
)

sidecar = exact(
    sidecar,
    '''            append("Choose exactly one safe next UI action that best reproduces the recorded intent. ")
            append("Recorded target: ")''',
    '''            append("Recover using bounded steps until the recorded action can actually be reproduced. ")
            append("Recorded action type: $rescueExpectedAction. ")
            append("Recorded target: ")''',
    "rescue goal semantics",
)

sidecar = exact(
    sidecar,
    '''        if (missionStep >= 40 || failureCount >= 8) {
            finishMission(false, "retry/step limit")
            return
        }''',
    '''        val maxSteps = if (rescueMode) 6 else 40
        val maxFailures = if (rescueMode) 3 else 8
        if (missionStep >= maxSteps || failureCount >= maxFailures) {
            if (rescueMode) finishRescue(false) else finishMission(false, "retry/step limit")
            return
        }''',
    "bounded rescue limits",
)

sidecar = exact(
    sidecar,
    '''                if (command.action == "DONE") {
                    finishMission(true, command.payload.ifBlank { "Task complete" })
                    return@askPhysicalAi
                }
                if (command.action == "FAIL") {
                    finishMission(false, command.payload.ifBlank { "AI could not continue" })
                    return@askPhysicalAi
                }''',
    '''                if (command.action == "DONE") {
                    if (rescueMode) {
                        failTurn(run, "Rescue must reproduce the recorded $rescueExpectedAction before DONE")
                    } else {
                        finishMission(true, command.payload.ifBlank { "Task complete" })
                    }
                    return@askPhysicalAi
                }
                if (command.action == "FAIL") {
                    if (rescueMode) finishRescue(false)
                    else finishMission(false, command.payload.ifBlank { "AI could not continue" })
                    return@askPhysicalAi
                }''',
    "rescue done/fail semantics",
)

sidecar = exact(
    sidecar,
    '''                            missionStep++
                            if (rescueMode) {
                                val cb = rescueCallback
                                rescueCallback = null
                                missionRunning = false
                                rescueMode = false
                                cb?.invoke(verified)
                            } else {
                                handler.postDelayed({ nextMissionTurn(run) }, 450L)
                            }''',
    '''                            missionStep++
                            if (rescueMode) {
                                val reproduced = verified && command.action == rescueExpectedAction
                                when {
                                    reproduced -> finishRescue(true)
                                    failureCount >= 3 || missionStep >= 6 -> finishRescue(false)
                                    else -> handler.postDelayed({ nextMissionTurn(run) }, 450L)
                                }
                            } else {
                                handler.postDelayed({ nextMissionTurn(run) }, 450L)
                            }''',
    "multi-turn rescue verification",
)

sidecar = exact(
    sidecar,
    '''        if (rescueMode) {
            val cb = rescueCallback
            rescueCallback = null
            missionRunning = false
            rescueMode = false
            cb?.invoke(false)
        } else if (failureCount >= 8) {
            finishMission(false, reason)
        } else {
            handler.postDelayed({ nextMissionTurn(run) }, 700L)
        }''',
    '''        val maxFailures = if (rescueMode) 3 else 8
        val maxSteps = if (rescueMode) 6 else 40
        if (failureCount >= maxFailures || missionStep >= maxSteps) {
            if (rescueMode) finishRescue(false) else finishMission(false, reason)
        } else {
            handler.postDelayed({ nextMissionTurn(run) }, 700L)
        }''',
    "rescue retry path",
)

sidecar = exact(
    sidecar,
    '''    private fun finishMission(ok: Boolean, message: String) {
        missionRunning = false''',
    '''    private fun finishRescue(ok: Boolean) {
        missionRunning = false
        waitingForAi = false
        val cb = rescueCallback
        rescueCallback = null
        rescueMode = false
        rescueExpectedAction = ""
        cb?.invoke(ok)
    }

    private fun finishMission(ok: Boolean, message: String) {
        missionRunning = false''',
    "finish rescue helper",
)

sidecar = exact(
    sidecar,
    '''        rescueMode = false
        val cb = rescueCallback''',
    '''        rescueMode = false
        rescueExpectedAction = ""
        val cb = rescueCallback''',
    "finish mission rescue reset",
)

sidecar = sub(
    sidecar,
    r'''(fun stop\(reason: String = "stopped"\) \{.*?        rescueMode = false\n)''',
    r'''\1        rescueExpectedAction = ""\n''',
    "stop rescue reset",
    re.S,
)

sidecar = exact(
    sidecar,
    '''            appendLine("LAST OUTCOME: $lastOutcome")
            appendLine("RECENT ACTION HISTORY:")''',
    '''            appendLine("LAST OUTCOME: $lastOutcome")
            if (rescueMode) {
                appendLine("RESCUE MODE: reproduce the recorded $rescueExpectedAction. You may use intermediate BACK, OPEN_APP, SCROLL or WAIT actions when needed.")
                appendLine("Do NOT return DONE in rescue mode. The executor will finish rescue only after a verified $rescueExpectedAction action.")
            }
            appendLine("RECENT ACTION HISTORY:")''',
    "rescue planner contract",
)

sidecar = exact(
    sidecar,
    '''    private fun waitForTargetWindow(run: Int, pkg: String, attempt: Int, callback: () -> Unit) {
        if (!alive(run)) return
        if (findRootForPackage(pkg) != null) {''',
    '''    private fun isPackageForeground(pkg: String): Boolean = try {
        service.windows.any { window ->
            window.root?.packageName?.toString() == pkg && (window.isActive || window.isFocused)
        } || service.rootInActiveWindow?.packageName?.toString() == pkg
    } catch (_: Throwable) {
        false
    }

    private fun waitForTargetWindow(run: Int, pkg: String, attempt: Int, callback: () -> Unit) {
        if (!alive(run)) return
        if (isPackageForeground(pkg)) {''',
    "foreground target verification",
)

# --- AutoActionService: failed rescue must fail closed instead of advancing playback. ---
auto = exact(
    auto,
    '''                    val rescueStarted = try {
                        aiSidecarController.rescueRecordedFailure(recordedGesture) { ok ->
                            if (ok) showTinyToast("AI rescue complete")
                            else showTinyToast("AI rescue failed")
                            finishOnce()
                        }
                    } catch (_: Throwable) {
                        false
                    }
                    if (!rescueStarted) {
                        showTinyToast("Target 10s me nahi mila")
                        finishOnce()
                    }''',
    '''                    val rescueStarted = try {
                        aiSidecarController.rescueRecordedFailure(recordedGesture) { ok ->
                            if (ok) {
                                showTinyToast("AI rescue complete")
                                finishOnce()
                            } else {
                                showTinyToast("AI rescue failed — playback stopped")
                                finishOnce()
                                if (isSamePlaybackRun(runId)) stopPlaybackInternal(showToast = false)
                            }
                        }
                    } catch (_: Throwable) {
                        false
                    }
                    if (!rescueStarted) {
                        showTinyToast("Target nahi mila — playback stopped")
                        finishOnce()
                        if (isSamePlaybackRun(runId)) stopPlaybackInternal(showToast = false)
                    }''',
    "fail-closed replay rescue",
)

sidecar_path.write_text(sidecar)
auto_path.write_text(auto)
print("AI recovery hardening patch applied")
