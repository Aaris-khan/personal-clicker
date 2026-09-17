package com.aarishkhan.aarishai

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas // AARISH_AI_VISUAL_IMPORTS_V4
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Rect
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.Display
import android.view.accessibility.AccessibilityNodeInfo
import android.widget.Toast
import androidx.core.content.FileProvider
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import java.io.File
import java.io.FileOutputStream
import java.util.Locale
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.abs

/**
 * AARISH_AI_SIDECAR_V1
 *
 * Physical ChatGPT/Gemini fallback + prompt-only autonomous mission controller.
 * AI decides the next bounded action; this app remains the executor/verifier.
 */
class AiSidecarController(private val service: AutoActionService) {

    enum class Provider(val packageName: String) {
        CHATGPT("com.openai.chatgpt"),
        GEMINI("com.google.android.apps.bard")
    }

    data class UiElement(
        val key: String,
        val packageName: String,
        val viewId: String,
        val text: String,
        val desc: String,
        val className: String,
        val bounds: Rect,
        val clickable: Boolean,
        val editable: Boolean,
        val enabled: Boolean
    )

    data class ScreenState(
        val packageName: String,
        val elements: List<UiElement>,
        val fingerprint: String,
        val screenshot: File?
    )

    private data class AiCommand(
        val action: String,
        val elementKey: String = "",
        val payload: String = "",
        val expected: String = ""
    )

    private val handler = Handler(Looper.getMainLooper())
    private val generation = AtomicInteger(0)

    @Volatile private var missionRunning = false
    @Volatile private var waitingForAi = false
    private var missionGoal = ""
    private var providerPreference = "AUTO"
    private var missionStep = 0
    private var failureCount = 0
    private var lastOutcome = "Mission started"
    private var lastTargetPackage = ""
    private var rescueCallback: ((Boolean) -> Unit)? = null
    private var rescueMode = false
    private var rescueExpectedAction = ""
    private val actionHistory = java.util.ArrayDeque<String>()

    // Mission-local provider health keeps AUTO from retrying a broken provider forever.
    private val providerFailureStreak = mutableMapOf<Provider, Int>()
    private val providerCooldownUntil = mutableMapOf<Provider, Long>()
    private var lastProviderAttempt: Provider? = null

    // Same target state + same command repeated is a planner loop, not useful progress.
    private var lastPlannerSignature = ""
    private var repeatedPlannerSignatureCount = 0

    fun isRunning(): Boolean = missionRunning || waitingForAi

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

    fun startMission(goal: String, provider: String = "AUTO"): Boolean {
        val clean = goal.replace(Regex("[\\u0000-\\u001F]+"), " ").trim().take(6000)
        if (clean.isBlank()) return false
        stop("restart")
        missionRunning = true
        rescueMode = false
        rescueExpectedAction = ""
        missionGoal = clean
        providerPreference = normalizeProviderPreference(provider)
        missionStep = 0
        failureCount = 0
        lastOutcome = "Mission started"
        resetProviderHealth()
        actionHistory.clear()
        rememberHistory("GOAL: $clean")
        val run = generation.incrementAndGet()
        toast("🤖 AI Mission started")
        handler.post { nextMissionTurn(run) }
        return true
    }

    fun rescueRecordedFailure(gesture: RecordedGesture, callback: (Boolean) -> Unit): Boolean {
        if (isRunning()) return false
        val target = listOfNotNull(
            gesture.targetText,
            gesture.targetDesc,
            gesture.targetId,
            gesture.targetClass,
            gesture.targetContextText
        ).filter { it.isNotBlank() }.joinToString(" | ").take(1800)
        rescueExpectedAction = inferRecordedAction(gesture)

        missionGoal = buildString {
            append("Recover one failed recorded automation step. ")
            append("The user had previously recorded a step and the local matcher could not find/execute it now. ")
            append("Recover using bounded steps until the recorded action can actually be reproduced. ")
            append("Recorded action type: $rescueExpectedAction. ")
            append("Recorded target: ")
            append(target.ifBlank { "unknown target" })
        }
        providerPreference = "AUTO"
        missionStep = 0
        failureCount = 0
        lastOutcome = "Recorded replay target missing"
        resetProviderHealth()
        actionHistory.clear()
        rememberHistory("RECORDED STEP FAILED: ${target.ifBlank { "unknown target" }}")
        rescueMode = true
        rescueCallback = callback
        missionRunning = true
        val run = generation.incrementAndGet()
        toast("🧠 AI rescue")
        handler.post { nextMissionTurn(run) }
        return true
    }

    fun stop(reason: String = "stopped") {
        // AARISH_AI_RESCUE_STOP_RELEASE_V3: stopping rescue must release playback waiter too.
        val pendingRescue = if (rescueMode) rescueCallback else null
        generation.incrementAndGet()
        missionRunning = false
        waitingForAi = false
        rescueMode = false
        rescueExpectedAction = ""
        rescueCallback = null
        handler.removeCallbacksAndMessages(null)
        try { pendingRescue?.invoke(false) } catch (_: Throwable) {}
        if (reason != "restart") toast("AI agent $reason")
    }

    private fun nextMissionTurn(run: Int) {
        if (!alive(run)) return
        val maxSteps = if (rescueMode) 6 else 40
        val maxFailures = if (rescueMode) 3 else 8
        if (missionStep >= maxSteps || failureCount >= maxFailures) {
            if (rescueMode) finishRescue(false) else finishMission(false, "retry/step limit")
            return
        }
        captureTargetScreen(run) { state ->
            if (!alive(run)) return@captureTargetScreen
            if (state == null || state.packageName.isBlank()) {
                failTurn(run, "Target screen not readable")
                return@captureTargetScreen
            }
            lastTargetPackage = state.packageName
            val provider = selectProvider()
            if (provider == null) {
                finishMission(false, "ChatGPT/Gemini installed nahi mila")
                return@captureTargetScreen
            }
            val requestId = "A${System.currentTimeMillis().toString(36)}${missionStep.toString(36)}"
            val prompt = buildPlannerPrompt(requestId, state)
            askPhysicalAi(run, provider, requestId, prompt, state.screenshot) { command ->
                if (!alive(run)) return@askPhysicalAi
                if (command == null) {
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

                if (command.action == "DONE") {
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
                }
                returnToTarget(run, lastTargetPackage) {
                    if (!alive(run)) return@returnToTarget
                    // AARISH_AI_CLIPBOARD_PROOF_V2: action se pehle clipboard baseline lo.
                    val clipboardBefore = readClipboard()
                    executeCommand(run, command, state) { executed, outcome ->
                        if (!alive(run)) return@executeCommand
                        if (!executed) {
                            failTurn(run, outcome)
                            return@executeCommand
                        }
                        verifyAfterAction(run, state, command, clipboardBefore) { verified, proof ->
                            if (!alive(run)) return@verifyAfterAction
                            lastOutcome = if (verified) "SUCCESS: $proof" else "UNCERTAIN: $proof"
                            rememberHistory("STEP $missionStep ${command.action} ${command.elementKey.ifBlank { "-" }} -> $lastOutcome")
                            if (!verified) failureCount++ else failureCount = (failureCount - 1).coerceAtLeast(0)
                            missionStep++
                            if (rescueMode) {
                                val reproduced = verified && command.action == rescueExpectedAction
                                when {
                                    reproduced -> finishRescue(true)
                                    failureCount >= 3 || missionStep >= 6 -> finishRescue(false)
                                    else -> handler.postDelayed({ nextMissionTurn(run) }, 450L)
                                }
                            } else {
                                handler.postDelayed({ nextMissionTurn(run) }, 450L)
                            }
                        }
                    }
                }
            }
        }
    }

    private fun failTurn(run: Int, reason: String) {
        if (!alive(run)) return
        failureCount++
        lastOutcome = "FAILED: $reason"
        rememberHistory("STEP $missionStep -> $lastOutcome")
        missionStep++
        val maxFailures = if (rescueMode) 3 else 8
        val maxSteps = if (rescueMode) 6 else 40
        if (failureCount >= maxFailures || missionStep >= maxSteps) {
            if (rescueMode) finishRescue(false) else finishMission(false, reason)
        } else {
            handler.postDelayed({ nextMissionTurn(run) }, 700L)
        }
    }

    private fun finishRescue(ok: Boolean) {
        missionRunning = false
        waitingForAi = false
        val cb = rescueCallback
        rescueCallback = null
        rescueMode = false
        rescueExpectedAction = ""
        cb?.invoke(ok)
    }

    private fun finishMission(ok: Boolean, message: String) {
        missionRunning = false
        waitingForAi = false
        rescueMode = false
        rescueExpectedAction = ""
        val cb = rescueCallback
        rescueCallback = null
        toast(if (ok) "✅ $message" else "⚠️ $message")
        cb?.invoke(ok)
    }

    private fun rememberHistory(entry: String) {
        val clean = entry.replace(Regex("\\s+"), " ").trim().take(360)
        if (clean.isBlank()) return
        while (actionHistory.size >= 12) actionHistory.removeFirst()
        actionHistory.addLast(clean)
    }

    private fun alive(run: Int): Boolean = missionRunning && generation.get() == run

    private fun normalizeProviderPreference(raw: String): String {
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

    private fun buildPlannerPrompt(requestId: String, state: ScreenState): String {
        val elements = state.elements.take(90).joinToString("\n") { e ->
            val label = listOf(e.text, e.desc).filter { it.isNotBlank() }.joinToString(" / ").take(140)
            "${e.key}|${e.className.substringAfterLast('.')}|${if (e.clickable) "C" else "-"}${if (e.editable) "E" else "-"}|$label|${e.bounds.left},${e.bounds.top},${e.bounds.right},${e.bounds.bottom}"
        }
        val history = actionHistory.joinToString("\n") { "- $it" }
        return buildString {
            appendLine("You are the recovery/planning brain for an Android UI automation agent.")
            appendLine("USER GOAL: $missionGoal")
            appendLine("REQUEST IDENTIFIER: $requestId")
            appendLine("STEP: $missionStep")
            appendLine("CURRENT PACKAGE: ${state.packageName}")
            appendLine("LAST OUTCOME: $lastOutcome")
            if (rescueMode) {
                appendLine("RESCUE MODE: reproduce the recorded $rescueExpectedAction. You may use intermediate BACK, OPEN_APP, SCROLL or WAIT actions when needed.")
                appendLine("Do NOT return DONE in rescue mode. The executor will finish rescue only after a verified $rescueExpectedAction action.")
            }
            appendLine("RECENT ACTION HISTORY:")
            appendLine(history.ifBlank { "- none" })
            appendLine("VISIBLE ACTIONABLE ELEMENTS:")
            appendLine(elements.ifBlank { "(no accessible actionable nodes)" })
            appendLine("A screenshot of this exact target state is attached when Android/provider sharing allows it.")
            appendLine("Clickable/editable candidates in the screenshot are visually marked with their E-number (E1, E2, ...). Use those markers plus the element list to ground your choice.")
            appendLine("Choose ONE next action only. Prefer a listed element key over guessing coordinates.")
            appendLine("Allowed actions: TAP, LONG_TAP, SET_TEXT, SCROLL (UP/DOWN), BACK, HOME, WAIT milliseconds, OPEN_APP by human app name, DONE, FAIL.")
            appendLine("For SCROLL use an element key when a scrollable container is listed; otherwise leave element empty and put UP or DOWN in the final field.")
            appendLine("Do not perform payments, purchases, money transfers, account deletion, installs/uninstalls, or permission/security changes autonomously.")
            // AARISH_AI_DONE_EVIDENCE_V3
            appendLine("Use DONE only when the CURRENT visible screen/state provides evidence that the user's goal is complete; never mark DONE from assumption or an earlier screen.")
            appendLine("Reply with ONE single machine line and no prose. Construct it as: word AARIS, two colons, request identifier, two colons, action name, two colons, element key or empty, two colons, payload/expected text.")
            appendLine("For SET_TEXT put the text to type in the final field. For WAIT put milliseconds in the final field. For OPEN_APP put the app name in the final field. For DONE/FAIL put a short reason in the final field.")
        }.take(15000)
    }

    private fun askPhysicalAi(
        run: Int,
        provider: Provider,
        requestId: String,
        prompt: String,
        screenshot: File?,
        callback: (AiCommand?) -> Unit
    ) {
        if (!alive(run)) return
        waitingForAi = true
        val opened = openProviderWithPayload(provider, prompt, screenshot)
        if (!opened) {
            waitingForAi = false
            callback(null)
            return
        }
        waitForProviderWindow(run, provider, 0) { root ->
            if (!alive(run)) return@waitForProviderWindow
            if (root == null) {
                waitingForAi = false
                callback(null)
                return@waitForProviderWindow
            }
            ensurePromptAndSend(run, provider, root, prompt) { sent ->
                if (!alive(run)) return@ensurePromptAndSend
                if (!sent) {
                    waitingForAi = false
                    callback(null)
                    return@ensurePromptAndSend
                }
                waitForCompleteResponse(run, provider, requestId, callback)
            }
        }
    }

    private fun openProviderWithPayload(provider: Provider, prompt: String, screenshot: File?): Boolean {
        if (screenshot != null && screenshot.exists()) {
            try {
                val uri = FileProvider.getUriForFile(service, "${service.packageName}.ai-files", screenshot)
                val send = Intent(Intent.ACTION_SEND).apply {
                    type = "image/png"
                    setPackage(provider.packageName)
                    putExtra(Intent.EXTRA_STREAM, uri)
                    putExtra(Intent.EXTRA_TEXT, prompt)
                    clipData = ClipData.newUri(service.contentResolver, "Aarish AI screen", uri)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    if (Build.VERSION.SDK_INT >= 24) addFlags(Intent.FLAG_ACTIVITY_LAUNCH_ADJACENT)
                }
                service.startActivity(send)
                return true
            } catch (_: Throwable) {}
        }
        return try {
            val launch = service.packageManager.getLaunchIntentForPackage(provider.packageName) ?: return false
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
            if (Build.VERSION.SDK_INT >= 24) launch.addFlags(Intent.FLAG_ACTIVITY_LAUNCH_ADJACENT)
            service.startActivity(launch)
            true
        } catch (_: Throwable) { false }
    }

    private fun waitForProviderWindow(run: Int, provider: Provider, attempt: Int, callback: (AccessibilityNodeInfo?) -> Unit) {
        if (!alive(run)) return
        val root = findRootForPackage(provider.packageName)
        if (root != null) {
            handler.postDelayed({ callback(findRootForPackage(provider.packageName)) }, 450L)
            return
        }
        if (attempt >= 36) {
            callback(null)
            return
        }
        handler.postDelayed({ waitForProviderWindow(run, provider, attempt + 1, callback) }, 250L)
    }

    private fun ensurePromptAndSend(run: Int, provider: Provider, root: AccessibilityNodeInfo, prompt: String, callback: (Boolean) -> Unit) {
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

    private fun waitForCompleteResponse(run: Int, provider: Provider, requestId: String, callback: (AiCommand?) -> Unit) {
        val started = SystemClock.elapsedRealtime()
        var stableText = ""
        var stableCount = 0
        var sawGenerating = false

        fun poll() {
            if (!alive(run)) return
            val root = findRootForPackage(provider.packageName)
            if (root == null) {
                if (SystemClock.elapsedRealtime() - started > 120_000L) {
                    waitingForAi = false
                    callback(null)
                } else handler.postDelayed({ poll() }, 700L)
                return
            }

            val text = flattenText(root, 26000)
            val generating = hasGeneratingIndicator(root)
            if (generating) sawGenerating = true
            val parsed = parseCommand(text, requestId)

            if (text == stableText && text.isNotBlank()) stableCount++ else {
                stableText = text
                stableCount = 0
            }

            val complete = parsed != null && !generating && stableCount >= if (sawGenerating) 2 else 4
            if (complete) {
                waitingForAi = false
                callback(parsed)
                return
            }

            val elapsed = SystemClock.elapsedRealtime() - started
            if (elapsed > 120_000L) {
                // Last chance: OCR provider window so custom-rendered response can still be parsed.
                captureProviderOcr(provider) { ocr ->
                    waitingForAi = false
                    callback(parseCommand(ocr, requestId) ?: parsed)
                }
                return
            }
            handler.postDelayed({ poll() }, 700L)
        }
        handler.postDelayed({ poll() }, 900L)
    }

    private fun parseCommand(text: String, requestId: String): AiCommand? {
        val marker = "AARIS::$requestId::"
        val line = text.lineSequence().map { it.trim() }.lastOrNull { it.contains(marker) } ?: return null
        val start = line.indexOf(marker)
        if (start < 0) return null
        val raw = line.substring(start).take(4000)
        val parts = raw.split("::", limit = 5)
        if (parts.size < 4 || parts[0] != "AARIS" || parts[1] != requestId) return null
        val action = parts[2].trim().uppercase(Locale.US)
        val element = parts.getOrNull(3).orEmpty().trim()
        val payload = parts.getOrNull(4).orEmpty().trim()
        if (action !in setOf("TAP", "LONG_TAP", "SET_TEXT", "SCROLL", "BACK", "HOME", "WAIT", "OPEN_APP", "DONE", "FAIL")) return null
        return AiCommand(action = action, elementKey = element, payload = payload, expected = payload)
    }

    private fun returnToTarget(run: Int, pkg: String, callback: () -> Unit) {
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

    private fun isPackageForeground(pkg: String): Boolean = try {
        service.windows.any { window ->
            window.root?.packageName?.toString() == pkg && (window.isActive || window.isFocused)
        } || service.rootInActiveWindow?.packageName?.toString() == pkg
    } catch (_: Throwable) {
        false
    }

    private fun waitForTargetWindow(run: Int, pkg: String, attempt: Int, callback: () -> Unit) {
        if (!alive(run)) return
        if (isPackageForeground(pkg)) {
            handler.postDelayed({ if (alive(run)) callback() }, 180L)
            return
        }
        if (attempt >= 24) {
            failTurn(run, "Target app did not return to foreground")
            return
        }
        handler.postDelayed({ waitForTargetWindow(run, pkg, attempt + 1, callback) }, 250L)
    }

    private fun executeCommand(run: Int, command: AiCommand, state: ScreenState, callback: (Boolean, String) -> Unit) {
        if (!alive(run)) return
        if (isSensitive(command, state)) {
            toast("⚠️ Sensitive action paused — user confirmation required")
            callback(false, "Sensitive action blocked")
            return
        }
        when (command.action) {
            // AARISH_AI_RICH_ACTIONS_V2
            "BACK" -> callback(service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK), "Back")
            "HOME" -> callback(service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME), "Home")
            "WAIT" -> {
                val ms = command.payload.filter { it.isDigit() }.toLongOrNull()?.coerceIn(250L, 15_000L) ?: 1000L
                handler.postDelayed({ if (alive(run)) callback(true, "Waited ${ms}ms") }, ms)
            }
            "OPEN_APP" -> callback(openAppByLabel(command.payload), "Open app ${command.payload}")
            "TAP", "LONG_TAP", "SET_TEXT" -> {
                val saved = state.elements.firstOrNull { it.key.equals(command.elementKey, true) }
                if (saved == null) {
                    callback(false, "Unknown element ${command.elementKey}")
                    return
                }
                val live = findBestLiveMatch(saved)
                if (live == null) {
                    callback(false, "Element became stale")
                    return
                }
                if (command.action == "SET_TEXT") {
                    val args = Bundle().apply {
                        putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, command.payload.take(12000))
                    }
                    val ok = try { live.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args) } catch (_: Throwable) { false }
                    callback(ok, "Set text ${saved.key}")
                } else if (command.action == "LONG_TAP") {
                    callback(longClickNode(live), "Long tapped ${saved.key}")
                } else {
                    callback(clickNode(live), "Tapped ${saved.key}")
                }
            }
            "SCROLL" -> {
                val direction = command.payload.trim().uppercase(Locale.US)
                val saved = state.elements.firstOrNull { it.key.equals(command.elementKey, true) }
                val live = saved?.let { findBestLiveMatch(it) } ?: findScrollableNode()
                if (live == null) {
                    callback(false, "Scrollable container not found")
                } else {
                    val action = if (direction.contains("UP") || direction.contains("BACK"))
                        AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
                    else AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
                    val ok = try { live.performAction(action) } catch (_: Throwable) { false }
                    callback(ok, "Scrolled ${if (action == AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD) "UP" else "DOWN"}")
                }
            }
            else -> callback(false, "Unsupported action")
        }
    }

    private fun verifyAfterAction(
        run: Int,
        before: ScreenState,
        command: AiCommand,
        clipboardBefore: String,
        callback: (Boolean, String) -> Unit
    ) {
        if (!alive(run)) return
        val started = SystemClock.elapsedRealtime()
        fun poll(attempt: Int) {
            if (!alive(run)) return
            val now = captureStateWithoutScreenshot()
            val changed = now != null && now.fingerprint != before.fingerprint
            val clipChanged = readClipboard().let { it.isNotBlank() && it != clipboardBefore }
            if (changed || clipChanged || command.action == "WAIT") {
                callback(true, when {
                    changed -> "screen state changed"
                    clipChanged -> "clipboard changed"
                    else -> "action completed"
                })
                return
            }
            if (attempt >= 14 || SystemClock.elapsedRealtime() - started > 4500L) {
                callback(false, "no observable state change")
                return
            }
            handler.postDelayed({ poll(attempt + 1) }, 300L)
        }
        handler.postDelayed({ poll(0) }, 250L)
    }

    private fun captureTargetScreen(run: Int, callback: (ScreenState?) -> Unit) {
        val base = captureStateWithoutScreenshot()
        if (base == null) { callback(null); return }
        val windowId = findTargetWindowId(base.packageName)
        val windowBounds = findWindowBoundsForPackage(base.packageName)
        captureScreenshot(windowId, windowBounds, base.elements) { file ->
            if (!alive(run)) return@captureScreenshot
            callback(base.copy(screenshot = file))
        }
    }

    private fun captureStateWithoutScreenshot(): ScreenState? {
        val root = findBestTargetRoot() ?: return null
        val pkg = root.packageName?.toString().orEmpty()
        val elements = collectActionable(root, pkg)
        val fingerprint = buildFingerprint(pkg, elements)
        return ScreenState(pkg, elements, fingerprint, null)
    }

    private fun captureScreenshot(
        windowId: Int?,
        windowBounds: Rect?,
        elements: List<UiElement>,
        callback: (File?) -> Unit
    ) {
        if (Build.VERSION.SDK_INT < 30) { callback(null); return }
        val windowCapture = Build.VERSION.SDK_INT >= 34 && windowId != null && windowId >= 0
        val cb = object : AccessibilityService.TakeScreenshotCallback {
            override fun onSuccess(screenshot: AccessibilityService.ScreenshotResult) {
                val buffer = screenshot.hardwareBuffer
                try {
                    val hw = Bitmap.wrapHardwareBuffer(buffer, screenshot.colorSpace)
                    val bitmap = hw?.copy(Bitmap.Config.ARGB_8888, true)
                    val grounded = bitmap?.let { annotateScreenshotForAi(it, elements, if (windowCapture) windowBounds else null) }
                    callback(grounded?.let { saveBitmap(it) })
                    if (grounded !== bitmap) grounded?.recycle()
                    bitmap?.recycle()
                } catch (_: Throwable) {
                    callback(null)
                } finally {
                    try { buffer.close() } catch (_: Throwable) {}
                }
            }
            override fun onFailure(errorCode: Int) { callback(null) }
        }
        try {
            if (windowCapture) {
                service.takeScreenshotOfWindow(windowId!!, service.mainExecutor, cb)
            } else {
                service.takeScreenshot(Display.DEFAULT_DISPLAY, service.mainExecutor, cb)
            }
        } catch (_: Throwable) { callback(null) }
    }

    private fun annotateScreenshotForAi(bitmap: Bitmap, elements: List<UiElement>, windowBounds: Rect?): Bitmap {
        // AARISH_AI_GROUNDED_SCREENSHOT_V4: draw sparse E# labels so AI chooses our live candidates, not guessed pixels.
        val out = if (bitmap.isMutable) bitmap else bitmap.copy(Bitmap.Config.ARGB_8888, true)
        val canvas = Canvas(out)
        val density = service.resources.displayMetrics.density.coerceAtLeast(1f)
        val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 2.2f * density
            color = Color.rgb(255, 64, 64)
        }
        val badge = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.FILL
            color = Color.argb(225, 15, 15, 15)
        }
        val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.FILL
            color = Color.WHITE
            textSize = 12f * density
            typeface = Typeface.DEFAULT_BOLD
        }

        val originX = windowBounds?.left ?: 0
        val originY = windowBounds?.top ?: 0
        val sourceW = (windowBounds?.width() ?: service.resources.displayMetrics.widthPixels).coerceAtLeast(1)
        val sourceH = (windowBounds?.height() ?: service.resources.displayMetrics.heightPixels).coerceAtLeast(1)
        val sx = out.width.toFloat() / sourceW.toFloat()
        val sy = out.height.toFloat() / sourceH.toFloat()
        val maxArea = out.width.toLong() * out.height.toLong()

        elements.asSequence()
            .filter { it.clickable || it.editable }
            .take(70)
            .forEach { e ->
                val left = ((e.bounds.left - originX) * sx).coerceIn(0f, out.width.toFloat())
                val top = ((e.bounds.top - originY) * sy).coerceIn(0f, out.height.toFloat())
                val right = ((e.bounds.right - originX) * sx).coerceIn(0f, out.width.toFloat())
                val bottom = ((e.bounds.bottom - originY) * sy).coerceIn(0f, out.height.toFloat())
                if (right <= left + 2f || bottom <= top + 2f) return@forEach
                val area = ((right - left) * (bottom - top)).toLong()
                if (area > maxArea * 3L / 4L) return@forEach

                canvas.drawRect(left, top, right, bottom, stroke)
                val label = e.key
                val pad = 3f * density
                val badgeW = textPaint.measureText(label) + pad * 2f
                val badgeH = textPaint.textSize + pad * 2f
                val bx = left.coerceAtMost((out.width - badgeW).coerceAtLeast(0f))
                val by = (top - badgeH).takeIf { it >= 0f } ?: top
                canvas.drawRect(bx, by, bx + badgeW, (by + badgeH).coerceAtMost(out.height.toFloat()), badge)
                canvas.drawText(label, bx + pad, (by + badgeH - pad).coerceAtMost(out.height.toFloat()), textPaint)
            }
        return out
    }

    private fun saveBitmap(bitmap: Bitmap): File? = try {
        val dir = File(service.cacheDir, "ai_sidecar").apply { mkdirs() }
        dir.listFiles()?.filter { System.currentTimeMillis() - it.lastModified() > 10 * 60_000L }?.forEach { it.delete() }
        val file = File(dir, "screen_${UUID.randomUUID()}.png")
        FileOutputStream(file).use { bitmap.compress(Bitmap.CompressFormat.PNG, 92, it) }
        file
    } catch (_: Throwable) { null }

    private fun captureProviderOcr(provider: Provider, callback: (String) -> Unit) {
        if (Build.VERSION.SDK_INT < 30) { callback(""); return }
        val windowId = findWindowIdForPackage(provider.packageName)
        val cb = object : AccessibilityService.TakeScreenshotCallback {
            override fun onSuccess(screenshot: AccessibilityService.ScreenshotResult) {
                val buffer = screenshot.hardwareBuffer
                try {
                    val hw = Bitmap.wrapHardwareBuffer(buffer, screenshot.colorSpace)
                    val bitmap = hw?.copy(Bitmap.Config.ARGB_8888, false)
                    if (bitmap == null) { callback(""); return }
                    val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
                    recognizer.process(InputImage.fromBitmap(bitmap, 0))
                        .addOnSuccessListener { callback(it.text.orEmpty()) }
                        .addOnFailureListener { callback("") }
                        .addOnCompleteListener { bitmap.recycle(); recognizer.close() }
                } catch (_: Throwable) { callback("") }
                finally { try { buffer.close() } catch (_: Throwable) {} }
            }
            override fun onFailure(errorCode: Int) { callback("") }
        }
        try {
            if (Build.VERSION.SDK_INT >= 34 && windowId != null) service.takeScreenshotOfWindow(windowId, service.mainExecutor, cb)
            else service.takeScreenshot(Display.DEFAULT_DISPLAY, service.mainExecutor, cb)
        } catch (_: Throwable) { callback("") }
    }

    private fun findBestTargetRoot(): AccessibilityNodeInfo? {
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

    private fun findRootForPackage(pkg: String): AccessibilityNodeInfo? = try {
        service.windows.asSequence().mapNotNull { it.root }.firstOrNull { it.packageName?.toString() == pkg }
            ?: service.rootInActiveWindow?.takeIf { it.packageName?.toString() == pkg }
    } catch (_: Throwable) { null }

    private fun findWindowIdForPackage(pkg: String): Int? = try {
        service.windows.firstOrNull { it.root?.packageName?.toString() == pkg }?.id
    } catch (_: Throwable) { null }

    private fun findTargetWindowId(pkg: String): Int? = findWindowIdForPackage(pkg)

    private fun findWindowBoundsForPackage(pkg: String): Rect? = try {
        var best: Rect? = null
        var bestScore = Int.MIN_VALUE
        for (window in service.windows) {
            val root = window.root ?: continue
            if (root.packageName?.toString() != pkg) continue
            val b = Rect()
            try { root.getBoundsInScreen(b) } catch (_: Throwable) {}
            if (b.width() <= 0 || b.height() <= 0) continue
            var score = b.width() * b.height() / 1000
            if (window.isActive) score += 100000
            if (window.isFocused) score += 120000
            score += window.layer.coerceIn(-100, 100) * 10
            if (score > bestScore) { bestScore = score; best = Rect(b) }
        }
        best
    } catch (_: Throwable) { null }

    private fun collectActionable(root: AccessibilityNodeInfo, pkg: String): List<UiElement> {
        val out = ArrayList<UiElement>()
        val stack = java.util.ArrayDeque<AccessibilityNodeInfo>()
        stack.add(root)
        var seen = 0
        while (stack.isNotEmpty() && seen < 5000 && out.size < 140) {
            val node = stack.removeLast(); seen++
            val visible = try { node.isVisibleToUser } catch (_: Throwable) { false }
            val enabled = try { node.isEnabled } catch (_: Throwable) { false }
            val clickable = try { node.isClickable } catch (_: Throwable) { false }
            val editable = try { node.isEditable } catch (_: Throwable) { false }
            val text = node.text?.toString().orEmpty().trim().take(300)
            val desc = node.contentDescription?.toString().orEmpty().trim().take(300)
            val id = try { node.viewIdResourceName.orEmpty() } catch (_: Throwable) { "" }
            val cls = node.className?.toString().orEmpty()
            val b = Rect(); try { node.getBoundsInScreen(b) } catch (_: Throwable) {}
            if (visible && enabled && b.width() > 0 && b.height() > 0 && (clickable || editable || text.isNotBlank() || desc.isNotBlank())) {
                out.add(UiElement("E${out.size + 1}", pkg, id, text, desc, cls, Rect(b), clickable, editable, enabled))
            }
            val count = try { node.childCount } catch (_: Throwable) { 0 }
            for (i in 0 until count) try { node.getChild(i)?.let(stack::add) } catch (_: Throwable) {}
        }
        return out
    }

    private fun buildFingerprint(pkg: String, elements: List<UiElement>): String {
        val raw = buildString {
            append(pkg)
            elements.take(100).forEach { e ->
                append('|').append(e.viewId).append(':').append(e.text.take(70)).append(':').append(e.desc.take(70))
                    .append(':').append(e.bounds.left / 12).append(',').append(e.bounds.top / 12)
            }
        }
        return raw.hashCode().toString(16)
    }

    private fun findEditable(root: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        var best: AccessibilityNodeInfo? = null
        var bestScore = Int.MIN_VALUE
        walk(root, 3500) { n ->
            val editable = try { n.isEditable } catch (_: Throwable) { false }
            val enabled = try { n.isEnabled } catch (_: Throwable) { false }
            val visible = try { n.isVisibleToUser } catch (_: Throwable) { false }
            if (!editable || !enabled || !visible) return@walk
            val text = (n.text?.toString().orEmpty() + " " + n.contentDescription?.toString().orEmpty()).lowercase(Locale.US)
            var score = 100
            if (try { n.isFocused } catch (_: Throwable) { false }) score += 80
            if (text.contains("message") || text.contains("ask") || text.contains("prompt") || text.contains("chat")) score += 40
            val b = Rect(); try { n.getBoundsInScreen(b) } catch (_: Throwable) {}
            score += (b.top / 100).coerceAtMost(30)
            if (score > bestScore) { bestScore = score; best = n }
        }
        return best
    }

    private fun findSendNode(root: AccessibilityNodeInfo, composer: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        val cb = Rect(); try { composer?.getBoundsInScreen(cb) } catch (_: Throwable) {}
        var best: AccessibilityNodeInfo? = null
        var bestScore = Int.MIN_VALUE
        walk(root, 4000) { n ->
            if (!(try { n.isClickable && n.isEnabled && n.isVisibleToUser } catch (_: Throwable) { false })) return@walk
            val label = (n.text?.toString().orEmpty() + " " + n.contentDescription?.toString().orEmpty() + " " + try { n.viewIdResourceName.orEmpty() } catch (_: Throwable) { "" }).lowercase(Locale.US)
            var score = 0
            if (Regex("(^|\\W)(send|submit)(\\W|$)").containsMatchIn(label)) score += 500
            if (label.contains("arrow_up") || label.contains("send_message")) score += 360
            if (label.contains("voice") || label.contains("mic") || label.contains("attach")) score -= 260
            // AARISH_AI_SEND_GUARD_V2: unrelated send/share controls ko composer Send se neeche rakho.
            if (label.contains("feedback") || label.contains("share") || label.contains("send to")) score -= 420
            val b = Rect(); try { n.getBoundsInScreen(b) } catch (_: Throwable) {}
            if (!cb.isEmpty) {
                val dx = abs(b.centerX() - cb.right)
                val dy = abs(b.centerY() - cb.centerY())
                score += (240 - (dx + dy) / 4).coerceAtLeast(-100)
            }
            if (score > bestScore) { bestScore = score; best = n }
        }
        return best.takeIf { bestScore >= 260 }
    }

    private fun hasGeneratingIndicator(root: AccessibilityNodeInfo): Boolean {
        var found = false
        walk(root, 2500) { n ->
            if (found) return@walk
            val label = (n.text?.toString().orEmpty() + " " + n.contentDescription?.toString().orEmpty()).lowercase(Locale.US)
            val exact = label.trim()
            val clickable = try { n.isClickable } catch (_: Throwable) { false }
            // AARISH_AI_GENERATION_DETECT_V2
            if (label.contains("stop generating") || label.contains("stop response") || label.contains("cancel response") ||
                label.contains("interrupt response") || (clickable && exact == "stop")) {
                found = true
            }
        }
        return found
    }

    private fun flattenText(root: AccessibilityNodeInfo, maxChars: Int): String {
        val lines = LinkedHashSet<String>()
        walk(root, 5000) { n ->
            listOf(n.text?.toString(), n.contentDescription?.toString()).forEach { s ->
                val clean = s.orEmpty().replace(Regex("\\s+"), " ").trim()
                if (clean.isNotBlank() && clean.length <= 5000) lines.add(clean)
            }
        }
        return lines.joinToString("\n").takeLast(maxChars)
    }

    private fun walk(root: AccessibilityNodeInfo, limit: Int, visit: (AccessibilityNodeInfo) -> Unit) {
        val stack = java.util.ArrayDeque<AccessibilityNodeInfo>()
        stack.add(root); var count = 0
        while (stack.isNotEmpty() && count++ < limit) {
            val n = stack.removeLast(); visit(n)
            val c = try { n.childCount } catch (_: Throwable) { 0 }
            for (i in 0 until c) try { n.getChild(i)?.let(stack::add) } catch (_: Throwable) {}
        }
    }

    private fun findScrollableNode(): AccessibilityNodeInfo? {
        val root = findBestTargetRoot() ?: return null
        var best: AccessibilityNodeInfo? = null
        var bestArea = -1
        walk(root, 4500) { n ->
            val scrollable = try { n.isScrollable && n.isVisibleToUser && n.isEnabled } catch (_: Throwable) { false }
            if (!scrollable) return@walk
            val b = Rect(); try { n.getBoundsInScreen(b) } catch (_: Throwable) {}
            val area = b.width().coerceAtLeast(0) * b.height().coerceAtLeast(0)
            if (area > bestArea) { bestArea = area; best = n }
        }
        return best
    }

    private fun longClickNode(node: AccessibilityNodeInfo): Boolean {
        try { if (node.performAction(AccessibilityNodeInfo.ACTION_LONG_CLICK)) return true } catch (_: Throwable) {}
        val b = Rect(); try { node.getBoundsInScreen(b) } catch (_: Throwable) { return false }
        if (b.isEmpty || Build.VERSION.SDK_INT < 24) return false
        val path = Path().apply { moveTo(b.exactCenterX(), b.exactCenterY()) }
        return try {
            val gesture = GestureDescription.Builder()
                .addStroke(GestureDescription.StrokeDescription(path, 0L, 650L))
                .build()
            service.dispatchGesture(gesture, null, null)
        } catch (_: Throwable) { false }
    }

    private fun clickNode(node: AccessibilityNodeInfo): Boolean {
        try { if (node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true } catch (_: Throwable) {}
        var p: AccessibilityNodeInfo? = try { node.parent } catch (_: Throwable) { null }
        repeat(6) {
            val cur = p ?: return@repeat
            try { if (cur.isClickable && cur.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true } catch (_: Throwable) {}
            p = try { cur.parent } catch (_: Throwable) { null }
        }
        val b = Rect(); try { node.getBoundsInScreen(b) } catch (_: Throwable) { return false }
        if (b.isEmpty || Build.VERSION.SDK_INT < 24) return false
        val path = Path().apply { moveTo(b.exactCenterX(), b.exactCenterY()) }
        return try {
            val gesture = GestureDescription.Builder().addStroke(GestureDescription.StrokeDescription(path, 0L, 90L)).build()
            service.dispatchGesture(gesture, null, null)
        } catch (_: Throwable) { false }
    }

    private fun findBestLiveMatch(saved: UiElement): AccessibilityNodeInfo? {
        val root = findRootForPackage(saved.packageName) ?: findBestTargetRoot() ?: return null
        var best: AccessibilityNodeInfo? = null
        var bestScore = Int.MIN_VALUE
        walk(root, 5000) { n ->
            if (!(try { n.isVisibleToUser && n.isEnabled } catch (_: Throwable) { false })) return@walk
            val id = try { n.viewIdResourceName.orEmpty() } catch (_: Throwable) { "" }
            val text = n.text?.toString().orEmpty().trim()
            val desc = n.contentDescription?.toString().orEmpty().trim()
            val cls = n.className?.toString().orEmpty()
            val b = Rect(); try { n.getBoundsInScreen(b) } catch (_: Throwable) {}
            var score = 0
            if (saved.viewId.isNotBlank() && id == saved.viewId) score += 700
            if (saved.desc.isNotBlank() && desc.equals(saved.desc, true)) score += 450
            if (saved.text.isNotBlank() && text.equals(saved.text, true)) score += 380
            if (saved.className.isNotBlank() && cls == saved.className) score += 90
            if (saved.editable == (try { n.isEditable } catch (_: Throwable) { false })) score += 45
            if (saved.clickable == (try { n.isClickable } catch (_: Throwable) { false })) score += 35
            val dist = abs(b.centerX() - saved.bounds.centerX()) + abs(b.centerY() - saved.bounds.centerY())
            score += (180 - dist / 8).coerceAtLeast(-120)
            if (score > bestScore) { bestScore = score; best = n }
        }
        return best.takeIf { bestScore >= 260 }
    }

    private fun isSensitive(command: AiCommand, state: ScreenState): Boolean {
        val element = state.elements.firstOrNull { it.key.equals(command.elementKey, true) }
        val text = listOf(missionGoal, command.payload, element?.text.orEmpty(), element?.desc.orEmpty(), element?.viewId.orEmpty()).joinToString(" ").lowercase(Locale.US)
        val blocked = listOf(
            "pay now", "payment", "send money", "transfer money", "bank transfer", "purchase", "buy now",
            "delete account", "close account", "uninstall", "install app", "allow permission", "grant permission",
            "factory reset", "erase data", "confirm order", "otp", "one time password", "password",
            "passcode", "upi pin", "security pin", "cvv"
        )
        return blocked.any(text::contains)
    }

    private fun openAppByLabel(labelRaw: String): Boolean {
        val wanted = labelRaw.trim().lowercase(Locale.US)
        if (wanted.isBlank()) return false
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
            } ?: return false
            val appLabel = info.loadLabel(service.packageManager)?.toString().orEmpty().lowercase(Locale.US)
            if (!(appLabel == wanted || appLabel.contains(wanted) || wanted.contains(appLabel))) return false
            val pkg = info.activityInfo.packageName
            val launch = service.packageManager.getLaunchIntentForPackage(pkg) ?: return false
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
            service.startActivity(launch)
            true
        } catch (_: Throwable) { false }
    }

    private fun readClipboard(): String = try {
        val cm = service.getSystemService(Context.CLIPBOARD_SERVICE) as? android.content.ClipboardManager
        val clip = cm?.primaryClip
        if (clip != null && clip.itemCount > 0) clip.getItemAt(0).coerceToText(service)?.toString().orEmpty().take(3000) else ""
    } catch (_: Throwable) { "" }

    private fun toast(message: String) {
        handler.post { Toast.makeText(service, message.take(220), Toast.LENGTH_SHORT).show() }
    }
}
