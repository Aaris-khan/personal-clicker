from pathlib import Path
import re

p = Path("app/src/main/java/com/aarishkhan/aarishai/AiSidecarController.kt")
s = p.read_text()


def exact(old: str, new: str, label: str, expected: int = 1) -> None:
    global s
    count = s.count(old)
    if count != expected:
        raise SystemExit(f"{label}: expected {expected} exact match(es), found {count}")
    s = s.replace(old, new)


def sub(pattern: str, replacement: str, label: str, flags: int = 0) -> None:
    global s
    s, count = re.subn(pattern, replacement, s, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 regex match, found {count}")


sub(
    r'''    private var lastOutcome = "Mission started"\n    private var currentProvider: Provider\? = null\n    private var lastTargetPackage = ""\n    private var lastCapturedElements: List<UiElement> = emptyList\(\)\n    private var rescueCallback: \(\(Boolean\) -> Unit\)\? = null\n    private var rescueMode = false\n    // AARISH_AI_MISSION_HISTORY_V4: compact bounded history gives the planner memory without huge prompts\.\n    private val actionHistory = java\.util\.ArrayDeque<String>\(\)''',
    '''    private var lastOutcome = "Mission started"
    private var lastTargetPackage = ""
    private var rescueCallback: ((Boolean) -> Unit)? = null
    private var rescueMode = false
    private val actionHistory = java.util.ArrayDeque<String>()

    // Mission-local provider health keeps AUTO from retrying a broken provider forever.
    private val providerFailureStreak = mutableMapOf<Provider, Int>()
    private val providerCooldownUntil = mutableMapOf<Provider, Long>()
    private var lastProviderAttempt: Provider? = null

    // Same target state + same command repeated is a planner loop, not useful progress.
    private var lastPlannerSignature = ""
    private var repeatedPlannerSignatureCount = 0''',
    "state fields",
)

exact(
    '        providerPreference = provider.trim().uppercase(Locale.US).ifBlank { "AUTO" }',
    '        providerPreference = normalizeProviderPreference(provider)',
    "provider preference normalization",
)

sub(
    r'''(fun startMission\(goal: String, provider: String = "AUTO"\): Boolean \{.*?        lastOutcome = "Mission started"\n)''',
    r'''\1        resetProviderHealth()\n''',
    "mission health reset",
    re.S,
)

sub(
    r'''(fun rescueRecordedFailure\(gesture: RecordedGesture, callback: \(Boolean\) -> Unit\): Boolean \{.*?        lastOutcome = "Recorded replay target missing"\n)''',
    r'''\1        resetProviderHealth()\n''',
    "rescue health reset",
    re.S,
)

exact('            lastCapturedElements = state.elements\n', '', "remove stale element cache")
exact('            currentProvider = provider\n', '', "remove unused current provider")

sub(
    r'''                if \(command == null\) \{\n                    // AARISH_AI_NULL_RESPONSE_RETURN_V3: timeout/parse failure must not strand provider UI\.\n                    returnToTarget\(run, lastTargetPackage\) \{\n                        if \(alive\(run\)\) failTurn\(run, "AI response parse/timeout"\)\n                    \}\n                    return@askPhysicalAi\n                \}\n                if \(command\.action == "DONE"\) \{''',
    '''                if (command == null) {
                    markProviderFailure(provider, "open/send/response failure")
                    returnToTarget(run, lastTargetPackage) {
                        if (alive(run)) failTurn(run, "AI response parse/timeout")
                    }
                    return@askPhysicalAi
                }
                markProviderSuccess(provider)

                val plannerSignature = listOf(
                    state.fingerprint,
                    command.action,
                    command.elementKey,
                    command.payload.take(180)
                ).joinToString("|")
                if (plannerSignature == lastPlannerSignature) {
                    repeatedPlannerSignatureCount++
                } else {
                    lastPlannerSignature = plannerSignature
                    repeatedPlannerSignatureCount = 1
                }
                if (repeatedPlannerSignatureCount >= 3 && command.action !in setOf("WAIT", "DONE", "FAIL")) {
                    markProviderFailure(provider, "repeated identical plan")
                    rememberHistory("LOOP BREAKER: repeated ${command.action} ${command.elementKey}")
                    returnToTarget(run, lastTargetPackage) {
                        if (alive(run)) failTurn(run, "AI repeated same action without progress")
                    }
                    return@askPhysicalAi
                }

                if (command.action == "DONE") {''',
    "provider failover and planner loop breaker",
)

exact(
    '                                cb?.invoke(verified || executed)',
    '                                cb?.invoke(verified)',
    "rescue proof requirement",
)

sub(
    r'''    private fun selectProvider\(\): Provider\? \{.*?\n    \}\n\n    private fun buildPlannerPrompt''',
    '''    private fun normalizeProviderPreference(raw: String): String {
        val normalized = raw.trim().uppercase(Locale.US)
        return if (normalized in setOf("AUTO", "CHATGPT", "GEMINI")) normalized else "AUTO"
    }

    private fun resetProviderHealth() {
        providerFailureStreak.clear()
        providerCooldownUntil.clear()
        lastProviderAttempt = null
        lastPlannerSignature = ""
        repeatedPlannerSignatureCount = 0
    }

    private fun providerInstalled(provider: Provider): Boolean = try {
        service.packageManager.getLaunchIntentForPackage(provider.packageName) != null
    } catch (_: Throwable) {
        false
    }

    private fun markProviderFailure(provider: Provider, reason: String) {
        if (providerPreference != "AUTO") return
        val streak = (providerFailureStreak[provider] ?: 0) + 1
        providerFailureStreak[provider] = streak
        val cooldown = (15_000L * streak).coerceAtMost(90_000L)
        providerCooldownUntil[provider] = SystemClock.elapsedRealtime() + cooldown
        lastProviderAttempt = provider
        rememberHistory("PROVIDER ${provider.name} failed ($reason), failover armed")
    }

    private fun markProviderSuccess(provider: Provider) {
        providerFailureStreak[provider] = 0
        providerCooldownUntil.remove(provider)
        lastProviderAttempt = provider
    }

    private fun selectProvider(): Provider? {
        val installed = Provider.values().filter(::providerInstalled)
        if (installed.isEmpty()) return null

        when (providerPreference) {
            "CHATGPT" -> return Provider.CHATGPT.takeIf(::providerInstalled)
            "GEMINI" -> return Provider.GEMINI.takeIf(::providerInstalled)
        }

        val now = SystemClock.elapsedRealtime()
        val ready = installed.filter { (providerCooldownUntil[it] ?: 0L) <= now }
        if (ready.isNotEmpty()) {
            return ready.minWithOrNull(
                compareBy<Provider>(
                    { providerFailureStreak[it] ?: 0 },
                    { if (it == lastProviderAttempt) 0 else 1 },
                    { it.ordinal }
                )
            )
        }

        return installed.minByOrNull { providerCooldownUntil[it] ?: Long.MAX_VALUE }
    }

    private fun buildPlannerPrompt''',
    "health-aware provider selector",
    re.S,
)

sub(
    r'''    private fun ensurePromptAndSend\(run: Int, provider: Provider, root: AccessibilityNodeInfo, prompt: String, callback: \(Boolean\) -> Unit\) \{.*?\n    \}\n\n    private fun waitForCompleteResponse''',
    '''    private fun ensurePromptAndSend(run: Int, provider: Provider, root: AccessibilityNodeInfo, prompt: String, callback: (Boolean) -> Unit) {
        if (!alive(run)) return
        val composer = findEditable(root)
        if (composer == null) {
            callback(false)
            return
        }

        val setOk = try {
            val args = Bundle().apply {
                putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, prompt)
            }
            composer.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
        } catch (_: Throwable) {
            false
        }

        if (!setOk) {
            val existing = try { composer.text?.toString().orEmpty() } catch (_: Throwable) { "" }
            val proof = prompt.take(96)
            if (proof.isNotBlank() && !existing.contains(proof)) {
                callback(false)
                return
            }
        }

        handler.postDelayed({
            if (!alive(run)) return@postDelayed
            val latest = findRootForPackage(provider.packageName)
            val latestComposer = latest?.let(::findEditable)
            val send = latest?.let { findSendNode(it, latestComposer ?: composer) }
            val ok = send != null && clickNode(send)
            if (ok) {
                callback(true)
            } else {
                handler.postDelayed({
                    if (!alive(run)) return@postDelayed
                    val retryRoot = findRootForPackage(provider.packageName)
                    val retryComposer = retryRoot?.let(::findEditable)
                    val retry = retryRoot?.let { findSendNode(it, retryComposer ?: composer) }
                    callback(retry != null && clickNode(retry))
                }, 800L)
            }
        }, 650L)
    }

    private fun waitForCompleteResponse''',
    "prompt insertion and send proof",
    re.S,
)

timeout_count = s.count("210_000L")
if timeout_count != 2:
    raise SystemExit(f"AI timeout: expected 2 matches, found {timeout_count}")
s = s.replace("210_000L", "120_000L")

sub(
    r'''    private fun returnToTarget\(run: Int, pkg: String, callback: \(\) -> Unit\) \{.*?\n    \}\n\n    private fun executeCommand''',
    '''    private fun returnToTarget(run: Int, pkg: String, callback: () -> Unit) {
        if (!alive(run)) return
        if (pkg.isBlank() || pkg == service.packageName) {
            callback()
            return
        }

        var moved = false
        try {
            val am = service.getSystemService(Context.ACTIVITY_SERVICE) as? android.app.ActivityManager
            @Suppress("DEPRECATION")
            val tasks = am?.getRecentTasks(50, android.app.ActivityManager.RECENT_IGNORE_UNAVAILABLE).orEmpty()
            val hit = tasks.firstOrNull { info ->
                info.baseIntent?.component?.packageName == pkg || info.origActivity?.packageName == pkg
            }
            if (hit != null && am != null) {
                try {
                    am.moveTaskToFront(hit.id, 0)
                    moved = true
                } catch (_: Throwable) {}
            }
        } catch (_: Throwable) {}

        if (!moved) {
            try {
                val launch = service.packageManager.getLaunchIntentForPackage(pkg)
                if (launch != null) {
                    launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                    service.startActivity(launch)
                }
            } catch (_: Throwable) {}
        }

        waitForTargetWindow(run, pkg, 0, callback)
    }

    private fun waitForTargetWindow(run: Int, pkg: String, attempt: Int, callback: () -> Unit) {
        if (!alive(run)) return
        if (findRootForPackage(pkg) != null) {
            handler.postDelayed({ if (alive(run)) callback() }, 180L)
            return
        }
        if (attempt >= 24) {
            failTurn(run, "Target app did not return to foreground")
            return
        }
        handler.postDelayed({ waitForTargetWindow(run, pkg, attempt + 1, callback) }, 250L)
    }

    private fun executeCommand''',
    "verified target restoration",
    re.S,
)

exact(
    '            if (changed || clipChanged || command.action in setOf("WAIT", "OPEN_APP")) {',
    '            if (changed || clipChanged || command.action == "WAIT") {',
    "OPEN_APP verification",
)

exact(
    '        val text = listOf(command.payload, element?.text.orEmpty(), element?.desc.orEmpty(), element?.viewId.orEmpty()).joinToString(" ").lowercase(Locale.US)',
    '        val text = listOf(missionGoal, command.payload, element?.text.orEmpty(), element?.desc.orEmpty(), element?.viewId.orEmpty()).joinToString(" ").lowercase(Locale.US)',
    "sensitive mission context",
)

exact(
    '            "factory reset", "erase data", "confirm order"',
    '            "factory reset", "erase data", "confirm order", "otp", "one time password", "password",\n            "passcode", "upi pin", "security pin", "cvv"',
    "credential guard",
)

p.write_text(s)
print("AI sidecar hardening patch applied")
