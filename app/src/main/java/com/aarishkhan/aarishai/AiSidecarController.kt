package com.aarishkhan.aarishai

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Path
import android.graphics.Rect
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
    private var currentProvider: Provider? = null
    private var lastTargetPackage = ""
    private var lastCapturedElements: List<UiElement> = emptyList()
    private var rescueCallback: ((Boolean) -> Unit)? = null
    private var rescueMode = false

    fun isRunning(): Boolean = missionRunning || waitingForAi

    fun startMission(goal: String, provider: String = "AUTO"): Boolean {
        val clean = goal.replace(Regex("[\\u0000-\\u001F]+"), " ").trim().take(6000)
        if (clean.isBlank()) return false
        stop("restart")
        missionRunning = true
        rescueMode = false
        missionGoal = clean
        providerPreference = provider.trim().uppercase(Locale.US).ifBlank { "AUTO" }
        missionStep = 0
        failureCount = 0
        lastOutcome = "Mission started"
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

        missionGoal = buildString {
            append("Recover one failed recorded automation step. ")
            append("The user had previously recorded a step and the local matcher could not find/execute it now. ")
            append("Choose exactly one safe next UI action that best reproduces the recorded intent. ")
            append("Recorded target: ")
            append(target.ifBlank { "unknown target" })
        }
        providerPreference = "AUTO"
        missionStep = 0
        failureCount = 0
        lastOutcome = "Recorded replay target missing"
        rescueMode = true
        rescueCallback = callback
        missionRunning = true
        val run = generation.incrementAndGet()
        toast("🧠 AI rescue")
        handler.post { nextMissionTurn(run) }
        return true
    }

    fun stop(reason: String = "stopped") {
        generation.incrementAndGet()
        missionRunning = false
        waitingForAi = false
        rescueMode = false
        rescueCallback = null
        handler.removeCallbacksAndMessages(null)
        if (reason != "restart") toast("AI agent $reason")
    }

    private fun nextMissionTurn(run: Int) {
        if (!alive(run)) return
        if (missionStep >= 40 || failureCount >= 8) {
            finishMission(false, "retry/step limit")
            return
        }
        captureTargetScreen(run) { state ->
            if (!alive(run)) return@captureTargetScreen
            if (state == null || state.packageName.isBlank()) {
                failTurn(run, "Target screen not readable")
                return@captureTargetScreen
            }
            lastTargetPackage = state.packageName
            lastCapturedElements = state.elements
            val provider = selectProvider()
            if (provider == null) {
                finishMission(false, "ChatGPT/Gemini installed nahi mila")
                return@captureTargetScreen
            }
            currentProvider = provider
            val requestId = "A${System.currentTimeMillis().toString(36)}${missionStep.toString(36)}"
            val prompt = buildPlannerPrompt(requestId, state)
            askPhysicalAi(run, provider, requestId, prompt, state.screenshot) { command ->
                if (!alive(run)) return@askPhysicalAi
                if (command == null) {
                    failTurn(run, "AI response parse/timeout")
                    return@askPhysicalAi
                }
                if (command.action == "DONE") {
                    finishMission(true, command.payload.ifBlank { "Task complete" })
                    return@askPhysicalAi
                }
                if (command.action == "FAIL") {
                    finishMission(false, command.payload.ifBlank { "AI could not continue" })
                    return@askPhysicalAi
                }
                returnToTarget(run, lastTargetPackage) {
                    if (!alive(run)) return@returnToTarget
                    executeCommand(run, command, state) { executed, outcome ->
                        if (!alive(run)) return@executeCommand
                        if (!executed) {
                            failTurn(run, outcome)
                            return@executeCommand
                        }
                        verifyAfterAction(run, state, command) { verified, proof ->
                            if (!alive(run)) return@verifyAfterAction
                            lastOutcome = if (verified) "SUCCESS: $proof" else "UNCERTAIN: $proof"
                            if (!verified) failureCount++ else failureCount = (failureCount - 1).coerceAtLeast(0)
                            missionStep++
                            if (rescueMode) {
                                val cb = rescueCallback
                                rescueCallback = null
                                missionRunning = false
                                rescueMode = false
                                cb?.invoke(verified || executed)
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
        missionStep++
        if (rescueMode) {
            val cb = rescueCallback
            rescueCallback = null
            missionRunning = false
            rescueMode = false
            cb?.invoke(false)
        } else if (failureCount >= 8) {
            finishMission(false, reason)
        } else {
            handler.postDelayed({ nextMissionTurn(run) }, 700L)
        }
    }

    private fun finishMission(ok: Boolean, message: String) {
        missionRunning = false
        waitingForAi = false
        rescueMode = false
        val cb = rescueCallback
        rescueCallback = null
        toast(if (ok) "✅ $message" else "⚠️ $message")
        cb?.invoke(ok)
    }

    private fun alive(run: Int): Boolean = missionRunning && generation.get() == run

    private fun selectProvider(): Provider? {
        fun installed(p: Provider): Boolean = try {
            service.packageManager.getLaunchIntentForPackage(p.packageName) != null
        } catch (_: Throwable) { false }

        return when (providerPreference) {
            "CHATGPT" -> Provider.CHATGPT.takeIf(::installed)
            "GEMINI" -> Provider.GEMINI.takeIf(::installed)
            else -> listOf(Provider.CHATGPT, Provider.GEMINI).firstOrNull(::installed)
        }
    }

    private fun buildPlannerPrompt(requestId: String, state: ScreenState): String {
        val elements = state.elements.take(90).joinToString("\n") { e ->
            val label = listOf(e.text, e.desc).filter { it.isNotBlank() }.joinToString(" / ").take(140)
            "${e.key}|${e.className.substringAfterLast('.')}|${if (e.clickable) "C" else "-"}${if (e.editable) "E" else "-"}|$label|${e.bounds.left},${e.bounds.top},${e.bounds.right},${e.bounds.bottom}"
        }
        return buildString {
            appendLine("You are the recovery/planning brain for an Android UI automation agent.")
            appendLine("USER GOAL: $missionGoal")
            appendLine("REQUEST IDENTIFIER: $requestId")
            appendLine("STEP: $missionStep")
            appendLine("CURRENT PACKAGE: ${state.packageName}")
            appendLine("LAST OUTCOME: $lastOutcome")
            appendLine("VISIBLE ACTIONABLE ELEMENTS:")
            appendLine(elements.ifBlank { "(no accessible actionable nodes)" })
            appendLine("A screenshot of this exact target state is attached when Android/provider sharing allows it.")
            appendLine("Choose ONE next action only. Prefer a listed element key over guessing coordinates.")
            appendLine("Allowed actions: TAP an element, SET_TEXT into an editable element, BACK, WAIT milliseconds, OPEN_APP by human app name, DONE, FAIL.")
            appendLine("Do not perform payments, purchases, money transfers, account deletion, installs/uninstalls, or permission/security changes autonomously.")
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
        if (composer != null) {
            try {
                val args = Bundle().apply {
                    putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, prompt)
                }
                composer.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
            } catch (_: Throwable) {}
        }
        handler.postDelayed({
            if (!alive(run)) return@postDelayed
            val latest = findRootForPackage(provider.packageName)
            val send = latest?.let { findSendNode(it, composer) }
            val ok = if (send != null) clickNode(send) else false
            if (ok) callback(true) else {
                handler.postDelayed({
                    val retryRoot = findRootForPackage(provider.packageName)
                    val retry = retryRoot?.let { findSendNode(it, findEditable(it)) }
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
                if (SystemClock.elapsedRealtime() - started > 210_000L) {
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
            if (elapsed > 210_000L) {
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
        if (action !in setOf("TAP", "SET_TEXT", "BACK", "WAIT", "OPEN_APP", "DONE", "FAIL")) return null
        return AiCommand(action = action, elementKey = element, payload = payload, expected = payload)
    }

    private fun returnToTarget(run: Int, pkg: String, callback: () -> Unit) {
        if (!alive(run)) return
        if (pkg.isBlank() || pkg == service.packageName) {
            callback(); return
        }
        try {
            val launch = service.packageManager.getLaunchIntentForPackage(pkg)
            if (launch != null) {
                launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                service.startActivity(launch)
            }
        } catch (_: Throwable) {}
        handler.postDelayed({ if (alive(run)) callback() }, 800L)
    }

    private fun executeCommand(run: Int, command: AiCommand, state: ScreenState, callback: (Boolean, String) -> Unit) {
        if (!alive(run)) return
        if (isSensitive(command, state)) {
            toast("⚠️ Sensitive action paused — user confirmation required")
            callback(false, "Sensitive action blocked")
            return
        }
        when (command.action) {
            "BACK" -> callback(service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK), "Back")
            "WAIT" -> {
                val ms = command.payload.filter { it.isDigit() }.toLongOrNull()?.coerceIn(250L, 15_000L) ?: 1000L
                handler.postDelayed({ if (alive(run)) callback(true, "Waited ${ms}ms") }, ms)
            }
            "OPEN_APP" -> callback(openAppByLabel(command.payload), "Open app ${command.payload}")
            "TAP", "SET_TEXT" -> {
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
                } else {
                    callback(clickNode(live), "Tapped ${saved.key}")
                }
            }
            else -> callback(false, "Unsupported action")
        }
    }

    private fun verifyAfterAction(run: Int, before: ScreenState, command: AiCommand, callback: (Boolean, String) -> Unit) {
        if (!alive(run)) return
        val beforeClip = readClipboard()
        val started = SystemClock.elapsedRealtime()
        fun poll(attempt: Int) {
            if (!alive(run)) return
            val now = captureStateWithoutScreenshot()
            val changed = now != null && now.fingerprint != before.fingerprint
            val clipChanged = readClipboard().let { it.isNotBlank() && it != beforeClip }
            if (changed || clipChanged || command.action in setOf("WAIT", "OPEN_APP")) {
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
        captureScreenshot(windowId) { file ->
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

    private fun captureScreenshot(windowId: Int?, callback: (File?) -> Unit) {
        if (Build.VERSION.SDK_INT < 30) { callback(null); return }
        val cb = object : AccessibilityService.TakeScreenshotCallback {
            override fun onSuccess(screenshot: AccessibilityService.ScreenshotResult) {
                val buffer = screenshot.hardwareBuffer
                try {
                    val hw = Bitmap.wrapHardwareBuffer(buffer, screenshot.colorSpace)
                    val bitmap = hw?.copy(Bitmap.Config.ARGB_8888, false)
                    callback(bitmap?.let { saveBitmap(it) })
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
            if (Build.VERSION.SDK_INT >= 34 && windowId != null && windowId >= 0) {
                service.takeScreenshotOfWindow(windowId, service.mainExecutor, cb)
            } else {
                service.takeScreenshot(Display.DEFAULT_DISPLAY, service.mainExecutor, cb)
            }
        } catch (_: Throwable) { callback(null) }
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

    private fun findRootForPackage(pkg: String): AccessibilityNodeInfo? = try {
        service.windows.asSequence().mapNotNull { it.root }.firstOrNull { it.packageName?.toString() == pkg }
            ?: service.rootInActiveWindow?.takeIf { it.packageName?.toString() == pkg }
    } catch (_: Throwable) { null }

    private fun findWindowIdForPackage(pkg: String): Int? = try {
        service.windows.firstOrNull { it.root?.packageName?.toString() == pkg }?.id
    } catch (_: Throwable) { null }

    private fun findTargetWindowId(pkg: String): Int? = findWindowIdForPackage(pkg)

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
            if (label.contains("stop generating") || label.contains("stop response") || label.contains("cancel response") || label.contains("interrupt response")) {
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
        val text = listOf(command.payload, element?.text.orEmpty(), element?.desc.orEmpty(), element?.viewId.orEmpty()).joinToString(" ").lowercase(Locale.US)
        val blocked = listOf(
            "pay now", "payment", "send money", "transfer money", "bank transfer", "purchase", "buy now",
            "delete account", "close account", "uninstall", "install app", "allow permission", "grant permission",
            "factory reset", "erase data", "confirm order"
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
