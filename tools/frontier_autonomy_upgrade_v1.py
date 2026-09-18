from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AI = ROOT / "app/src/main/java/com/aarishkhan/aarishai/AiSidecarController.kt"
AUTO = ROOT / "app/src/main/java/com/aarishkhan/aarishai/AutoActionService.kt"

def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

def replace_all_exact(path: Path, old: str, new: str, expected: int, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"{label}: expected {expected} matches in {path}, found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")

# ---------------------------------------------------------------------------
# Autonomous AI: mission progress ownership + hard deadline.
# ---------------------------------------------------------------------------
replace_once(
    AI,
'''    private var missionStep = 0
    private var failureCount = 0
    private var lastOutcome = "Mission started"
    private var lastTargetPackage = ""
''',
'''    private var missionStep = 0
    private var failureCount = 0
    private var lastOutcome = "Mission started"
    private var lastTargetPackage = ""

    // AARISH_AUTONOMY_PROGRESS_WATCHDOG_V1
    // A verified action is not automatically useful progress. Track the target state
    // across planning turns so repeated WAIT/no-op loops trigger failover instead of
    // burning the full step budget on an unchanged screen.
    private var missionStartedAt = 0L
    private var lastObservedTargetFingerprint = ""
    private var stagnantTargetTurns = 0
''',
    "add mission progress state"
)

replace_once(
    AI,
'''    private fun resetProviderHealth() {
        providerFailureStreak.clear()
        providerCooldownUntil.clear()
        lastProviderAttempt = null
        lastPlannerSignature = ""
        repeatedPlannerSignatureCount = 0
    }
''',
'''    private fun resetProviderHealth() {
        providerFailureStreak.clear()
        providerCooldownUntil.clear()
        lastProviderAttempt = null
        lastPlannerSignature = ""
        repeatedPlannerSignatureCount = 0
    }

    private fun resetMissionProgressWatchdog() {
        missionStartedAt = SystemClock.elapsedRealtime()
        lastObservedTargetFingerprint = ""
        stagnantTargetTurns = 0
    }
''',
    "add progress watchdog reset"
)

replace_all_exact(
    AI,
'''        resetProviderHealth()
        actionHistory.clear()
''',
'''        resetProviderHealth()
        resetMissionProgressWatchdog()
        actionHistory.clear()
''',
    2,
    "reset progress watchdog on mission/rescue start"
)

replace_once(
    AI,
'''        val maxSteps = if (rescueMode) 6 else 40
        val maxFailures = if (rescueMode) 3 else 8
        if (missionStep >= maxSteps || failureCount >= maxFailures) {
''',
'''        val maxSteps = if (rescueMode) 6 else 40
        val maxFailures = if (rescueMode) 3 else 8
        val runtimeLimitMs = if (rescueMode) 5L * 60L * 1000L else 30L * 60L * 1000L
        if (missionStartedAt > 0L &&
            SystemClock.elapsedRealtime() - missionStartedAt >= runtimeLimitMs
        ) {
            if (rescueMode) finishRescue(false)
            else finishMission(false, "mission runtime limit reached without verified completion")
            return
        }
        if (missionStep >= maxSteps || failureCount >= maxFailures) {
''',
    "add mission runtime deadline"
)

replace_once(
    AI,
'''            lastTargetPackage = state.packageName
            val provider = selectProvider(state.packageName)
''',
'''            // AARISH_AUTONOMY_PROGRESS_WATCHDOG_V1
            val sameTargetState =
                lastObservedTargetFingerprint.isNotBlank() &&
                    state.fingerprint == lastObservedTargetFingerprint &&
                    state.packageName == lastTargetPackage

            if (sameTargetState) {
                stagnantTargetTurns++
            } else {
                stagnantTargetTurns = 0
            }
            lastObservedTargetFingerprint = state.fingerprint

            if (stagnantTargetTurns >= 3) {
                val stalledProvider = lastProviderAttempt
                if (stalledProvider != null) {
                    markProviderFailure(stalledProvider, "target state unchanged across planning turns")
                }
                failureCount++
                lastOutcome = "NO_PROGRESS: target screen stayed unchanged across repeated turns"
                rememberHistory("NO-PROGRESS WATCHDOG: unchanged target state; provider failover/replan requested")
                stagnantTargetTurns = 0
                if (failureCount >= maxFailures) {
                    if (rescueMode) finishRescue(false)
                    else finishMission(false, "target state made no progress")
                    return@captureTargetScreen
                }
            }

            lastTargetPackage = state.packageName
            val provider = selectProvider(state.packageName)
''',
    "add no-progress detection before provider selection"
)

# ---------------------------------------------------------------------------
# Autonomous AI: stronger DONE proof. Package-only proof is valid for a true
# open-only goal, but not for "open app, then do X".
# ---------------------------------------------------------------------------
replace_once(
    AI,
'''    private fun verifyDoneEvidence(
        run: Int,
        planned: ScreenState,
        command: AiCommand,
        callback: (Boolean, String) -> Unit
    ) {
''',
'''    private fun missionAllowsPackageOnlyDone(): Boolean {
        val goal = normalizeUiText(missionGoal)
        if (goal.isBlank()) return false

        val openIntent = listOf(
            "open", "launch", "start", "switch to", "go to",
            "kholo", "khol", "chalao", "खोल", "खोलो", "चलाओ"
        ).any { goal.contains(it) }
        if (!openIntent) return false

        val beyondOpenIntent = listOf(
            "send", "message", "type", "write", "reply", "search", "find",
            "call", "share", "upload", "download", "select", "tap", "click",
            "bhej", "bhejo", "likh", "dhund", "dhoond", "भेज", "लिख",
            "ढूंढ", "खोज", "कॉल", "शेयर"
        ).any { goal.contains(it) }

        return !beyondOpenIntent
    }

    private fun verifyDoneEvidence(
        run: Int,
        planned: ScreenState,
        command: AiCommand,
        callback: (Boolean, String) -> Unit
    ) {
''',
    "add package-only done policy"
)

replace_once(
    AI,
'''        if (expected.equals("STATE_CHANGE", ignoreCase = true) ||
            expected.equals("CLIPBOARD_CHANGE", ignoreCase = true)
        ) {
            callback(false, "DONE needs concrete visible/package evidence")
            return
        }
        if (expectedMatchesState(live, expected)) {
''',
'''        if (expected.equals("STATE_CHANGE", ignoreCase = true) ||
            expected.equals("CLIPBOARD_CHANGE", ignoreCase = true)
        ) {
            callback(false, "DONE needs concrete visible/package evidence")
            return
        }

        if (expected.startsWith("PACKAGE=", ignoreCase = true) &&
            !missionAllowsPackageOnlyDone()
        ) {
            callback(false, "package-only proof is too weak for a multi-step goal")
            return
        }

        val normalizedProof = normalizeUiText(expected)
        if (normalizedProof in setOf(
                "done", "success", "successful", "complete", "completed",
                "task complete", "finished"
            )
        ) {
            callback(false, "generic completion words are not observable proof")
            return
        }

        if (expectedMatchesState(live, expected)) {
''',
    "strengthen done evidence"
)

# ---------------------------------------------------------------------------
# Autonomous AI: never rematch a saved E-key against a different application.
# ---------------------------------------------------------------------------
replace_once(
    AI,
'''    private fun findBestLiveMatch(saved: UiElement): AccessibilityNodeInfo? {
        val root = findRootForPackage(saved.packageName) ?: findBestTargetRoot() ?: return null
''',
'''    private fun findBestLiveMatch(saved: UiElement): AccessibilityNodeInfo? {
        // AARISH_LIVE_MATCH_PACKAGE_GUARD_V1
        // A stale E-key must never drift into another app just because a similar label
        // exists there. If the planner captured a package, fail closed until that exact
        // package has a live root and let the mission re-plan/recover.
        val wantedPackage = saved.packageName.trim()
        val root = if (wantedPackage.isNotBlank()) {
            findRootForPackage(wantedPackage) ?: return null
        } else {
            findBestTargetRoot() ?: return null
        }
        if (wantedPackage.isNotBlank()) {
            val livePackage = try { root.packageName?.toString().orEmpty() } catch (_: Throwable) { "" }
            if (!livePackage.equals(wantedPackage, ignoreCase = true)) return null
        }
''',
    "guard live matching by package"
)

# ---------------------------------------------------------------------------
# Autonomous AI: app-name launch resolution must reject ambiguous partial names.
# ---------------------------------------------------------------------------
replace_once(
    AI,
'''    private fun resolveLaunchPackageByLabel(labelRaw: String): String? {
        val wanted = labelRaw.trim().lowercase(Locale.US)
        if (wanted.isBlank()) return null
        return try {
            val q = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
            val matches = service.packageManager.queryIntentActivities(q, 0)
            val info = matches.maxByOrNull { r ->
                val label = r.loadLabel(service.packageManager)?.toString().orEmpty().lowercase(Locale.US)
                when {
                    label == wanted -> 1000
                    label.contains(wanted) || wanted.contains(label) -> 600
                    else -> 0
                }
            } ?: return null
            val appLabel = info.loadLabel(service.packageManager)?.toString().orEmpty().lowercase(Locale.US)
            if (!(appLabel == wanted || appLabel.contains(wanted) || wanted.contains(appLabel))) return null
            info.activityInfo.packageName
        } catch (_: Throwable) {
            null
        }
    }
''',
'''    private fun resolveLaunchPackageByLabel(labelRaw: String): String? {
        val wanted = normalizeUiText(labelRaw)
        if (wanted.isBlank()) return null
        return try {
            data class AppHit(val packageName: String, val score: Int)

            val q = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
            val matches = service.packageManager.queryIntentActivities(q, 0)
            val byPackage = linkedMapOf<String, Int>()

            for (r in matches) {
                val packageName = r.activityInfo?.packageName.orEmpty()
                if (packageName.isBlank()) continue
                val label = normalizeUiText(
                    r.loadLabel(service.packageManager)?.toString().orEmpty()
                )
                if (label.isBlank()) continue

                val score = when {
                    label == wanted -> 1000
                    label.startsWith("$wanted ") || wanted.startsWith("$label ") -> 780
                    label.contains(wanted) || wanted.contains(label) -> 620
                    else -> 0
                }
                if (score > (byPackage[packageName] ?: 0)) byPackage[packageName] = score
            }

            val ranked = byPackage
                .map { AppHit(it.key, it.value) }
                .filter { it.score > 0 }
                .sortedByDescending { it.score }

            val winner = ranked.firstOrNull() ?: return null
            if (winner.score < 620) return null
            val runner = ranked.drop(1).firstOrNull()
            if (winner.score < 1000 && runner != null && winner.score - runner.score < 120) {
                // Ambiguous partial app names are safer to re-plan than to launch the
                // wrong application and continue acting there.
                return null
            }
            winner.packageName
        } catch (_: Throwable) {
            null
        }
    }
''',
    "make app launch resolution ambiguity-safe"
)

# ---------------------------------------------------------------------------
# Recorded replay: after the explicit 30-minute availability wait, do not
# restart the whole workflow and create an infinite replay loop. Continue into
# the recorded step's own deterministic/visual resolver and guarded XY fallback.
# ---------------------------------------------------------------------------
replace_once(
    AUTO,
'''    val restartAsMaster = isMasterPlaybackInternal
    val restartOwner = if (restartAsMaster && masterWorkflowOwner.isNotBlank()) {
        masterWorkflowOwner
    } else {
        workflowOwner.ifBlank { initialConfigName }.ifBlank { GestureStore.getActiveConfigName(this) }
    }

''',
'''    // AARISH_30M_WAIT_CONTINUE_V1
    // Timeout belongs to this wait gate only. Replaying the complete workflow from
    // the beginning can loop forever and repeat already-completed actions.
''',
    "remove replay restart ownership from 30m wait"
)

replace_once(
    AUTO,
'''    fun restartAfterTimeout() {
        if (finished) return
        finished = true
        clearTask()
        if (!isCurrentCallbackRun(runId)) {
            finishActiveGesture(token)
            return
        }

        showTinyToast("AI WAIT 30min → restart")
        finishActiveGesture(token)

        val owner = restartOwner.trim()
        val masterMode = restartAsMaster
        stopPlaybackInternal(showToast = false)

        handler.postDelayed({
            if (instance !== this@AutoActionService || owner.isBlank()) return@postDelayed
            if (masterMode) playRecordedGestures(masterOwner = owner)
            else {
                GestureStore.setActiveConfigName(this@AutoActionService, owner)
                playRecordedGestures()
            }
        }, 700L)
    }
''',
'''    fun continueAfterTimeout() {
        if (finished) return
        if (!isCurrentCallbackRun(runId)) {
            finishWait()
            return
        }

        // Let the next recorded action execute its normal semantic + local visual
        // recovery pipeline. If that still fails, its guarded same-app XY fallback
        // is the final deterministic escape hatch.
        showTinyToast("Smart wait 30min → fallback path")
        finishWait()
    }
''',
    "replace 30m replay restart loop with continuation"
)

replace_once(
    AUTO,
'''            if (elapsed >= maxWaitMs) {
                restartAfterTimeout()
                return
            }
''',
'''            if (elapsed >= maxWaitMs) {
                continueAfterTimeout()
                return
            }
''',
    "wire 30m continuation"
)

# ---------------------------------------------------------------------------
# Recorded replay: after semantic + OCR/local visual rescue is exhausted, allow
# a last-resort XY tap ONLY on the same foreground package and matching
# orientation. This is intentionally tap-only; long-press/swipe remain fail-closed.
# ---------------------------------------------------------------------------
replace_once(
    AUTO,
'''                if (elapsed >= maxWait) {
                    // AARISH_NORMAL_REPLAY_NO_EXTERNAL_AI_V1
                    // A missing recorded target is a deterministic replay failure.
                    // Never open ChatGPT/Gemini or any model from this path.
                    showTinyToast("Target nahi mila — deterministic playback stopped")
                    finishOnce()
                    if (isSamePlaybackRun(runId)) stopPlaybackInternal(showToast = false)
                    return
                }
''',
'''                if (elapsed >= maxWait) {
                    // AARISH_SAME_APP_XY_LAST_RESORT_V1
                    // Semantic, OCR and local visual matching already had priority. For a
                    // simple recorded tap, use XY only when we can prove we are still in
                    // the same app and orientation. Never coordinate-fallback across apps.
                    val fallbackPoints = recordedGesture.points
                        .filter { !it.x.isNaN() && !it.x.isInfinite() && !it.y.isNaN() && !it.y.isInfinite() }
                        .sortedBy { it.t.coerceAtLeast(0L) }
                    val fallbackDuration = fallbackPoints.maxOfOrNull { it.t.coerceAtLeast(0L) } ?: 0L
                    val fallbackMovement = fallbackPoints.isNotEmpty() && hasRealMovement(fallbackPoints)
                    val savedPkg = recordedGesture.targetPackage?.trim().orEmpty()
                    val livePkg = try { aarishBestForegroundPackageForOcr()?.trim().orEmpty() } catch (_: Throwable) { "" }
                    val samePackage = savedPkg.isNotBlank() &&
                        livePkg.isNotBlank() &&
                        savedPkg.equals(livePkg, ignoreCase = true)

                    val screenW = resources.displayMetrics.widthPixels.toFloat().coerceAtLeast(1f)
                    val screenH = resources.displayMetrics.heightPixels.toFloat().coerceAtLeast(1f)
                    val orientationSafe =
                        recordedGesture.recordedScreenW <= 0 ||
                            recordedGesture.recordedScreenH <= 0 ||
                            ((recordedGesture.recordedScreenW > recordedGesture.recordedScreenH) == (screenW > screenH))

                    if (!fallbackMovement &&
                        fallbackDuration < 450L &&
                        hasSavedPercentAnchor(recordedGesture) &&
                        samePackage &&
                        orientationSafe
                    ) {
                        finished = true
                        currentTask?.let {
                            try { scheduledTasks.remove(it) } catch (_: Throwable) {}
                            try { handler.removeCallbacks(it) } catch (_: Throwable) {}
                        }

                        val x = (recordedGesture.xPercent.coerceIn(0f, 1f) * screenW)
                            .coerceIn(2f, (screenW - 2f).coerceAtLeast(2f))
                        val y = (recordedGesture.yPercent.coerceIn(0f, 1f) * screenH)
                            .coerceIn(2f, (screenH - 2f).coerceAtLeast(2f))

                        showTinyToast("Target unresolved → same-app XY fallback")
                        aarishDispatchTapWithToken(
                            x = x,
                            y = y,
                            runId = runId,
                            token = token,
                            label = "Guarded XY fallback",
                            tapDurationMs = 105L,
                            postGapMs = 90L
                        )
                        return
                    }

                    // AARISH_NORMAL_REPLAY_NO_EXTERNAL_AI_V1
                    // Cross-app / orientation-unsafe / non-tap misses remain fail-closed.
                    showTinyToast("Target nahi mila — safe fallback unavailable")
                    finishOnce()
                    if (isSamePlaybackRun(runId)) stopPlaybackInternal(showToast = false)
                    return
                }
''',
    "add guarded XY fallback after deterministic rescue"
)

# ---------------------------------------------------------------------------
# Static postconditions: fail the workflow before Gradle if patching drifted.
# ---------------------------------------------------------------------------
ai_text = AI.read_text(encoding="utf-8")
auto_text = AUTO.read_text(encoding="utf-8")

required_ai = [
    "AARISH_AUTONOMY_PROGRESS_WATCHDOG_V1",
    "AARISH_LIVE_MATCH_PACKAGE_GUARD_V1",
    "package-only proof is too weak for a multi-step goal",
    "Ambiguous partial app names are safer to re-plan",
]
required_auto = [
    "AARISH_30M_WAIT_CONTINUE_V1",
    "AARISH_SAME_APP_XY_LAST_RESORT_V1",
    "same-app XY fallback",
]
for marker in required_ai:
    if marker not in ai_text:
        raise SystemExit(f"missing AiSidecar marker: {marker}")
for marker in required_auto:
    if marker not in auto_text:
        raise SystemExit(f"missing AutoAction marker: {marker}")

if "AI WAIT 30min → restart" in auto_text:
    raise SystemExit("old 30-minute restart loop still present")

print("Frontier autonomy patch applied and static invariants verified.")
