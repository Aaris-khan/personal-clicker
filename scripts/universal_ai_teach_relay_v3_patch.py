from pathlib import Path
import re

ROOT = Path('app/src/main/java/com/aarishkhan/aarishai')
SIDE = ROOT / 'AiSidecarController.kt'
AUTO = ROOT / 'AutoActionService.kt'
FCS = ROOT / 'FloatingControlService.kt'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one marker, found {count}')
    return text.replace(old, new, 1)

# -----------------------------------------------------------------------------
# AutoActionService: provider calibration transaction.
# -----------------------------------------------------------------------------
a = AUTO.read_text(encoding='utf-8')
if 'AARISH_UNIVERSAL_AI_TEACH_CALIBRATION_V3' not in a:
    bridge_old = '''        fun isAiAgentRunning(): Boolean = instance?.aiSidecarController?.isRunning() == true

        // 🔥 Recording ke time button ki kundali nikalne ke liye
'''
    bridge_new = '''        fun isAiAgentRunning(): Boolean = instance?.aiSidecarController?.isRunning() == true

        // AARISH_UNIVERSAL_AI_TEACH_CALIBRATION_V3
        // One-time provider calibration: app fills a harmless prompt, user demonstrates
        // SEND and COPY, then only compact structural fingerprints are retained.
        fun startAiRelayTeaching(context: Context, provider: String): Boolean {
            val service = instance
            if (service == null) {
                Toast.makeText(context, "Accessibility Service ready nahi hai", Toast.LENGTH_SHORT).show()
                return false
            }
            if (service.aiSidecarController.isRunning()) {
                Toast.makeText(context, "AI mission chal rahi hai; pehle STOP karo", Toast.LENGTH_SHORT).show()
                return false
            }
            if (service.isPlayingInternal) service.stopPlaybackInternal()
            service.handler.post { service.startAiRelayTeachingInternalV3(provider) }
            return true
        }

        fun isAiRelayTrained(context: Context, provider: String): Boolean {
            val service = instance ?: return false
            val pkg = service.resolveAiTeachProviderPackageV3(provider)
            return pkg.isNotBlank() && AiTeachProfileStore.isReady(context, pkg)
        }

        // 🔥 Recording ke time button ki kundali nikalne ke liye
'''
    a = replace_once(a, bridge_old, bridge_new, 'AutoActionService companion bridge')

    field_old = '''    // AARISH_AI_SIDECAR_CONTROLLER_FIELD_V1
    private val aiSidecarController: AiSidecarController by lazy { AiSidecarController(this) }

    private val scheduledTasks = mutableListOf<Runnable>()
'''
    field_new = '''    // AARISH_AI_SIDECAR_CONTROLLER_FIELD_V1
    private val aiSidecarController: AiSidecarController by lazy { AiSidecarController(this) }

    // AARISH_UNIVERSAL_AI_TEACH_CALIBRATION_V3_IMPL
    private fun resolveAiTeachProviderPackageV3(raw: String): String {
        val clean = raw.trim()
        if (clean.startsWith("PKG:", ignoreCase = true)) {
            return clean.substringAfter(':').trim().take(220)
        }
        return when (clean.uppercase(java.util.Locale.US)) {
            "CHATGPT" -> "com.openai.chatgpt"
            "GEMINI" -> "com.google.android.apps.bard"
            "AUTO", "" -> listOf("com.openai.chatgpt", "com.google.android.apps.bard")
                .firstOrNull { pkg ->
                    try { packageManager.getLaunchIntentForPackage(pkg) != null } catch (_: Throwable) { false }
                }.orEmpty()
            else -> ""
        }
    }

    private fun findAiTeachRootV3(pkg: String): AccessibilityNodeInfo? {
        if (pkg.isBlank()) return null
        return try {
            val focused = windows.firstOrNull { w ->
                val root = w.root
                root?.packageName?.toString() == pkg && (w.isFocused || w.isActive)
            }?.root
            focused ?: windows.firstOrNull { it.root?.packageName?.toString() == pkg }?.root
                ?: rootInActiveWindow?.takeIf { it.packageName?.toString() == pkg }
        } catch (_: Throwable) {
            null
        }
    }

    private fun walkAiTeachV3(root: AccessibilityNodeInfo, limit: Int = 4500, visit: (AccessibilityNodeInfo) -> Unit) {
        val queue = java.util.ArrayDeque<AccessibilityNodeInfo>()
        queue.add(root)
        var seen = 0
        while (queue.isNotEmpty() && seen < limit) {
            val node = queue.removeFirst()
            seen++
            visit(node)
            val count = try { node.childCount } catch (_: Throwable) { 0 }
            for (i in 0 until count) {
                try { node.getChild(i)?.let(queue::addLast) } catch (_: Throwable) {}
            }
        }
    }

    private fun findAiTeachComposerV3(root: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        val h = resources.displayMetrics.heightPixels.coerceAtLeast(1)
        var best: AccessibilityNodeInfo? = null
        var bestScore = Int.MIN_VALUE
        walkAiTeachV3(root) { node ->
            val editable = try { node.isEditable } catch (_: Throwable) { false }
            val actions = try { node.actionList.orEmpty() } catch (_: Throwable) { emptyList() }
            val setText = actions.any { it.id == AccessibilityNodeInfo.ACTION_SET_TEXT }
            val visible = try { node.isVisibleToUser && node.isEnabled } catch (_: Throwable) { false }
            if (!visible || (!editable && !setText)) return@walkAiTeachV3
            val b = Rect(); try { node.getBoundsInScreen(b) } catch (_: Throwable) {}
            var score = 0
            if (editable) score += 300
            if (setText) score += 220
            if (b.centerY() >= h * 0.45f) score += 180
            if (b.width() >= resources.displayMetrics.widthPixels * 0.35f) score += 120
            val hint = buildString {
                append(try { node.text?.toString().orEmpty() } catch (_: Throwable) { "" })
                append(' ')
                append(try { node.contentDescription?.toString().orEmpty() } catch (_: Throwable) { "" })
            }.lowercase(java.util.Locale.US)
            if (listOf("message", "ask", "prompt", "type", "chat").any(hint::contains)) score += 100
            if (score > bestScore) { bestScore = score; best = node }
        }
        return best.takeIf { bestScore >= 300 }
    }

    private fun setAiTeachComposerTextV3(node: AccessibilityNodeInfo, text: String): Boolean {
        val args = android.os.Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        val direct = try {
            node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
            node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
        } catch (_: Throwable) { false }
        if (direct) return true

        val cm = try { getSystemService(Context.CLIPBOARD_SERVICE) as? android.content.ClipboardManager } catch (_: Throwable) { null }
            ?: return false
        val previous = try { cm.primaryClip } catch (_: Throwable) { null }
        val pasted = try {
            cm.setPrimaryClip(android.content.ClipData.newPlainText("Aaris AI calibration", text))
            node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
            node.performAction(AccessibilityNodeInfo.ACTION_PASTE)
        } catch (_: Throwable) { false }
        handler.postDelayed({
            try {
                if (previous != null) cm.setPrimaryClip(previous)
                else cm.setPrimaryClip(android.content.ClipData.newPlainText("", ""))
            } catch (_: Throwable) {}
        }, 900L)
        return pasted
    }

    private fun startAiRelayTeachingInternalV3(providerRaw: String) {
        val pkg = resolveAiTeachProviderPackageV3(providerRaw)
        if (pkg.isBlank()) {
            Toast.makeText(this, "Pehle usable AI provider select karo", Toast.LENGTH_LONG).show()
            return
        }
        val launch = try { packageManager.getLaunchIntentForPackage(pkg) } catch (_: Throwable) { null }
        if (launch == null) {
            Toast.makeText(this, "Selected AI app installed nahi mili", Toast.LENGTH_LONG).show()
            return
        }

        val token = "AARIS_TEACH_OK_" + java.util.UUID.randomUUID().toString().replace("-", "").take(8).uppercase(java.util.Locale.US)
        val calibrationPrompt = "AARIS UI relay calibration. Reply with exactly $token and nothing else."
        try {
            launch.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK or android.content.Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or android.content.Intent.FLAG_ACTIVITY_SINGLE_TOP)
            startActivity(launch)
        } catch (_: Throwable) {
            Toast.makeText(this, "AI app open nahi hui", Toast.LENGTH_LONG).show()
            return
        }

        fun waitComposer(attempt: Int) {
            val root = findAiTeachRootV3(pkg)
            val composer = root?.let(::findAiTeachComposerV3)
            if (composer != null && setAiTeachComposerTextV3(composer, calibrationPrompt)) {
                Toast.makeText(this, "🎓 Ab SEND button par ek baar tap karo", Toast.LENGTH_LONG).show()
                val fcs = FloatingControlService.instance
                if (fcs == null) {
                    Toast.makeText(this, "Floating controller ready nahi hai", Toast.LENGTH_LONG).show()
                    return
                }
                val armed = fcs.armAiTeachTapV3(AiTeachProfileStore.ROLE_SEND, pkg) { sendSnapshot ->
                    if (sendSnapshot == null) {
                        Toast.makeText(this, "SEND learn nahi hua; dobara Teach chalao", Toast.LENGTH_LONG).show()
                        return@armAiTeachTapV3
                    }
                    // Do not use a fixed AI wait. The transparent teaching layer simply waits
                    // for the user's next tap, so the user can tap COPY whenever generation is done.
                    handler.postDelayed({
                        Toast.makeText(this, "⏳ Reply complete hone do, phir us reply ka COPY tap karo", Toast.LENGTH_LONG).show()
                        fcs.armAiTeachTapV3(AiTeachProfileStore.ROLE_COPY, pkg) { copySnapshot ->
                            if (copySnapshot == null) {
                                Toast.makeText(this, "COPY learn nahi hua; dobara Teach chalao", Toast.LENGTH_LONG).show()
                                return@armAiTeachTapV3
                            }
                            val sendSaved = AiTeachProfileStore.saveVerifiedRole(this, pkg, AiTeachProfileStore.ROLE_SEND, sendSnapshot)
                            val copySaved = AiTeachProfileStore.saveVerifiedRole(this, pkg, AiTeachProfileStore.ROLE_COPY, copySnapshot)
                            val ready = sendSaved && copySaved && AiTeachProfileStore.isReady(this, pkg)
                            Toast.makeText(
                                this,
                                if (ready) "✅ AI relay trained: Send + Copy learned" else "⚠️ Training save verify nahi hua",
                                Toast.LENGTH_LONG
                            ).show()
                        }
                    }, 450L)
                }
                if (!armed) Toast.makeText(this, "Teach tap layer open nahi hui", Toast.LENGTH_LONG).show()
                return
            }
            if (attempt >= 60) {
                Toast.makeText(this, "AI composer ready nahi mila", Toast.LENGTH_LONG).show()
                return
            }
            handler.postDelayed({ waitComposer(attempt + 1) }, 200L)
        }
        handler.postDelayed({ waitComposer(0) }, 350L)
    }

    private val scheduledTasks = mutableListOf<Runnable>()
'''
    a = replace_once(a, field_old, field_new, 'AutoActionService implementation insertion')
    AUTO.write_text(a, encoding='utf-8')

# -----------------------------------------------------------------------------
# FloatingControlService: one-tap transparent teaching layer.
# -----------------------------------------------------------------------------
f = FCS.read_text(encoding='utf-8')
if 'AARISH_UNIVERSAL_AI_TEACH_TAP_LAYER_V3' not in f:
    marker = '''    fun isRecordingActive(): Boolean = isRecording

    // AARISH_AI_RECORDING_EXCLUSION_V4
'''
    insert = '''    fun isRecordingActive(): Boolean = isRecording

    // AARISH_UNIVERSAL_AI_TEACH_TAP_LAYER_V3
    private var aiTeachTapOverlayV3: android.view.View? = null
    private var aiTeachTapSerialV3: Int = 0

    private fun cancelAiTeachTapV3() {
        aiTeachTapSerialV3++
        val view = aiTeachTapOverlayV3
        aiTeachTapOverlayV3 = null
        if (view != null) {
            try { if (view.parent != null) aarishAccessWmV13().removeViewImmediate(view) } catch (_: Throwable) {
                try { if (view.parent != null) windowManager.removeViewImmediate(view) } catch (_: Throwable) {}
            }
        }
    }

    fun armAiTeachTapV3(
        role: String,
        providerPackage: String,
        callback: (TargetSnapshot?) -> Unit
    ): Boolean {
        if (android.os.Looper.myLooper() != android.os.Looper.getMainLooper()) {
            handler.post { armAiTeachTapV3(role, providerPackage, callback) }
            return true
        }
        if (isRecording) {
            Toast.makeText(this, "Normal recording pehle DONE karo", Toast.LENGTH_LONG).show()
            callback(null)
            return false
        }
        cancelAiTeachTapV3()
        val serial = aiTeachTapSerialV3
        val finished = java.util.concurrent.atomic.AtomicBoolean(false)
        val screenW = resources.displayMetrics.widthPixels.coerceAtLeast(2)
        val screenH = resources.displayMetrics.heightPixels.coerceAtLeast(2)
        val overlay = android.view.View(this).apply {
            setBackgroundColor(android.graphics.Color.TRANSPARENT)
            setOnTouchListener { _, event ->
                if (event.actionMasked != android.view.MotionEvent.ACTION_UP || !finished.compareAndSet(false, true)) {
                    return@setOnTouchListener true
                }
                val x = event.x.coerceIn(1f, (screenW - 1).toFloat())
                val y = event.y.coerceIn(1f, (screenH - 1).toFloat())
                val snapshot = AutoActionService.captureTargetSnapshot(x.toInt(), y.toInt(), screenW.toFloat(), screenH.toFloat())
                    ?.takeIf { it.targetPackage.orEmpty().equals(providerPackage, ignoreCase = true) }
                cancelAiTeachTapV3()

                val gesture = RecordedGesture(
                    delayFromStart = 0L,
                    points = listOf(GesturePoint(x, y, 0L)),
                    targetText = snapshot?.targetText,
                    targetDesc = snapshot?.targetDesc,
                    targetId = snapshot?.targetId,
                    targetClass = snapshot?.targetClass,
                    targetPackage = snapshot?.targetPackage ?: providerPackage,
                    targetContextText = snapshot?.targetContextText,
                    targetChildText = snapshot?.targetChildText,
                    targetSiblingText = snapshot?.targetSiblingText,
                    targetRoleFlags = snapshot?.targetRoleFlags,
                    targetTreePath = snapshot?.targetTreePath,
                    targetLeft = snapshot?.targetLeft ?: -1,
                    targetTop = snapshot?.targetTop ?: -1,
                    targetRight = snapshot?.targetRight ?: -1,
                    targetBottom = snapshot?.targetBottom ?: -1,
                    xPercent = snapshot?.xPercent ?: (x / screenW.toFloat()),
                    yPercent = snapshot?.yPercent ?: (y / screenH.toFloat()),
                    targetWPercent = snapshot?.targetWPercent ?: 0f,
                    targetHPercent = snapshot?.targetHPercent ?: 0f,
                    insideXPercent = snapshot?.insideXPercent ?: 0.5f,
                    insideYPercent = snapshot?.insideYPercent ?: 0.5f,
                    recordedScreenW = screenW,
                    recordedScreenH = screenH
                )
                handler.postDelayed({
                    AutoActionService.playSingleLiveGestureSafe(gesture) {
                        callback(snapshot)
                    }
                }, 70L)
                true
            }
        }
        aiTeachTapOverlayV3 = overlay
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            aarishAccessOverlayTypeV13(),
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = 0
            y = 0
        }
        return try {
            aarishAccessWmV13().addView(overlay, params)
            Toast.makeText(this, "🎓 $role tap karke sikhao", Toast.LENGTH_LONG).show()
            handler.postDelayed({
                if (aiTeachTapSerialV3 == serial && aiTeachTapOverlayV3 === overlay && finished.compareAndSet(false, true)) {
                    cancelAiTeachTapV3()
                    callback(null)
                }
            }, 120_000L)
            true
        } catch (_: Throwable) {
            aiTeachTapOverlayV3 = null
            callback(null)
            false
        }
    }

    // AARISH_AI_RECORDING_EXCLUSION_V4
'''
    f = replace_once(f, marker, insert, 'FloatingControlService teach layer')

    dialog_start = f.find('// AARISH_AI_MISSION_DIALOG_V1')
    dialog_end = f.find('private fun recordWaitAiAction()', dialog_start)
    if dialog_start < 0 or dialog_end < 0:
        raise SystemExit('Mission dialog block not found')
    block = f[dialog_start:dialog_end]
    block = replace_once(
        block,
        '''        .setPositiveButton("START", null)
        .setNegativeButton("Cancel", null)
        .create()
''',
        '''        .setPositiveButton("START", null)
        .setNeutralButton("🎓 TEACH AI", null)
        .setNegativeButton("Cancel", null)
        .create()
''',
        'mission dialog neutral button'
    )
    block = replace_once(
        block,
        '''    dialog.setOnShowListener {
        dialog.getButton(android.app.AlertDialog.BUTTON_POSITIVE)?.setOnClickListener {
''',
        '''    dialog.setOnShowListener {
        dialog.getButton(android.app.AlertDialog.BUTTON_NEUTRAL)?.setOnClickListener {
            if (!parkRecordingForAutonomousMission()) {
                Toast.makeText(this, "Recording safely park nahi hua", Toast.LENGTH_LONG).show()
                return@setOnClickListener
            }
            val teaching = AutoActionService.startAiRelayTeaching(this, provider)
            if (teaching) dialog.dismiss()
        }
        dialog.getButton(android.app.AlertDialog.BUTTON_POSITIVE)?.setOnClickListener {
''',
        'mission dialog teach listener'
    )
    block = block.replace(
        'Fixed coordinates nahi—UI badle to engine re-detect karta hai.',
        'Fixed coordinates nahi—UI badle to engine re-detect karta hai. First time 🎓 TEACH AI dabao: app prompt bharega, aap SEND aur reply ke baad COPY ek-ek baar tap karke sikhao.'
    )
    f = f[:dialog_start] + block + f[dialog_end:]
    FCS.write_text(f, encoding='utf-8')

# -----------------------------------------------------------------------------
# AiSidecarController: learned SEND fallback + learned COPY response fallback.
# -----------------------------------------------------------------------------
s = SIDE.read_text(encoding='utf-8')
if 'AARISH_UNIVERSAL_AI_TEACH_RUNTIME_V3' not in s:
    send_marker = '''    private fun findSendNode(root: AccessibilityNodeInfo, composer: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
'''
    learned_func = '''    // AARISH_UNIVERSAL_AI_TEACH_RUNTIME_V3
    // User-taught provider controls are a structural fallback, never a blind coordinate replay.
    // Native accessibility submit remains first choice; generic semantic discovery remains last choice.
    private fun findLearnedProviderControl(
        provider: Provider,
        root: AccessibilityNodeInfo,
        role: String
    ): AccessibilityNodeInfo? {
        val fp = AiTeachProfileStore.role(service, providerPackage(provider), role) ?: return null
        val sw = service.resources.displayMetrics.widthPixels.toFloat().coerceAtLeast(2f)
        val sh = service.resources.displayMetrics.heightPixels.toFloat().coerceAtLeast(2f)
        var best: AccessibilityNodeInfo? = null
        var bestScore = Int.MIN_VALUE
        walk(root, 4500) { n ->
            val usable = try { n.isClickable && n.isEnabled && n.isVisibleToUser } catch (_: Throwable) { false }
            if (!usable) return@walk
            val text = try { n.text?.toString().orEmpty() } catch (_: Throwable) { "" }
            val desc = try { n.contentDescription?.toString().orEmpty() } catch (_: Throwable) { "" }
            val id = try { n.viewIdResourceName.orEmpty() } catch (_: Throwable) { "" }
            val cls = try { n.className?.toString().orEmpty() } catch (_: Throwable) { "" }
            var score = 0
            if (fp.viewId.isNotBlank() && id.equals(fp.viewId, ignoreCase = true)) score += 900
            if (fp.desc.isNotBlank() && normalizeUiText(desc) == normalizeUiText(fp.desc)) score += 700
            if (fp.text.isNotBlank() && normalizeUiText(text) == normalizeUiText(fp.text)) score += 600
            if (fp.className.isNotBlank() && cls.equals(fp.className, ignoreCase = true)) score += 110

            val b = Rect(); try { n.getBoundsInScreen(b) } catch (_: Throwable) {}
            if (!fp.xPercent.isNaN() && !fp.yPercent.isNaN() && b.width() > 0 && b.height() > 0) {
                val dx = kotlin.math.abs((b.centerX() / sw) - fp.xPercent)
                val dy = kotlin.math.abs((b.centerY() / sh) - fp.yPercent)
                val distance = kotlin.math.sqrt(dx * dx + dy * dy)
                when {
                    distance <= 0.035f -> score += 280
                    distance <= 0.08f -> score += 220
                    distance <= 0.16f -> score += 140
                    distance <= 0.28f -> score += 60
                    else -> score -= 320
                }
                if (fp.wPercent > 0f) {
                    val dw = kotlin.math.abs((b.width() / sw) - fp.wPercent)
                    if (dw <= 0.05f) score += 70
                }
                if (fp.hPercent > 0f) {
                    val dh = kotlin.math.abs((b.height() / sh) - fp.hPercent)
                    if (dh <= 0.05f) score += 70
                }
            }
            if (score > bestScore) { bestScore = score; best = n }
        }
        return best.takeIf { bestScore >= 280 }
    }

''' + send_marker
    s = replace_once(s, send_marker, learned_func, 'sidecar learned control insertion')

    readiness_old = '''            val fallbackSubmitReady =
                latest != null && composer != null && findSendNode(latest, composer) != null
'''
    readiness_new = '''            val fallbackSubmitReady =
                latest != null && composer != null &&
                    (findLearnedProviderControl(provider, latest, AiTeachProfileStore.ROLE_SEND)
                        ?: findSendNode(latest, composer)) != null
'''
    s = replace_once(s, readiness_old, readiness_new, 'learned send readiness')

    send_old = '''            val send = latest?.let { findSendNode(it, freshComposer) }
'''
    send_new = '''            val send = latest?.let { rootNow ->
                findLearnedProviderControl(provider, rootNow, AiTeachProfileStore.ROLE_SEND)
                    ?: findSendNode(rootNow, freshComposer)
            }
'''
    s = replace_once(s, send_old, send_new, 'learned send click')

    wait_marker = '''    private fun waitForCompleteResponse(run: Int, provider: Provider, requestId: String, callback: (AiCommand?) -> Unit) {
'''
    copy_helper = '''    private fun findProviderScrollableForCopy(root: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        var best: AccessibilityNodeInfo? = null
        var bestArea = -1
        walk(root, 4500) { n ->
            val usable = try { n.isScrollable && n.isEnabled && n.isVisibleToUser } catch (_: Throwable) { false }
            if (!usable) return@walk
            val b = Rect(); try { n.getBoundsInScreen(b) } catch (_: Throwable) {}
            val area = b.width().coerceAtLeast(0) * b.height().coerceAtLeast(0)
            if (area > bestArea) { bestArea = area; best = n }
        }
        return best
    }

    private fun tryLearnedCopyResponse(
        run: Int,
        provider: Provider,
        requestId: String,
        callback: (AiCommand?) -> Unit
    ) {
        if (!alive(run)) return
        if (AiTeachProfileStore.role(service, providerPackage(provider), AiTeachProfileStore.ROLE_COPY) == null) {
            callback(null)
            return
        }
        val cm = try { service.getSystemService(Context.CLIPBOARD_SERVICE) as? android.content.ClipboardManager } catch (_: Throwable) { null }
        val previous = try { cm?.primaryClip } catch (_: Throwable) { null }
        var finished = false

        fun restoreClipboard() {
            try {
                if (cm != null) {
                    if (previous != null) cm.setPrimaryClip(previous)
                    else cm.setPrimaryClip(ClipData.newPlainText("", ""))
                }
            } catch (_: Throwable) {}
        }
        fun finish(command: AiCommand?) {
            if (finished) return
            finished = true
            restoreClipboard()
            callback(command)
        }
        fun readClipboardCommand(): AiCommand? {
            val text = try {
                val clip = cm?.primaryClip ?: return null
                if (clip.itemCount <= 0) return null
                clip.getItemAt(0).coerceToText(service)?.toString().orEmpty()
            } catch (_: Throwable) { "" }
            return parseCommand(text, requestId)
        }
        fun pollClipboard(attempt: Int) {
            if (!alive(run)) return
            readClipboardCommand()?.let { finish(it); return }
            if (attempt >= 14) { finish(null); return }
            handler.postDelayed({ pollClipboard(attempt + 1) }, 120L)
        }
        fun seek(scrolls: Int) {
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
    }

''' + wait_marker
    s = replace_once(s, wait_marker, copy_helper, 'learned copy helper insertion')

    old_ocr = '''            if (parsed == null &&
                !earlyOcrAttempted &&
                !generating &&
                (settledAfterGeneration || noGenerationSignalButSlow)
            ) {
                earlyOcrAttempted = true
                captureProviderOcr(provider) { ocr ->
                    if (!alive(run)) return@captureProviderOcr
                    val fromOcr = parseCommand(ocr, requestId)
                    if (fromOcr != null) {
                        waitingForAi = false
                        callback(fromOcr)
                    } else {
                        handler.postDelayed({ if (alive(run)) poll() }, 320L)
                    }
                }
                return
            }
'''
    new_ocr = '''            if (parsed == null &&
                !earlyOcrAttempted &&
                !generating &&
                (settledAfterGeneration || noGenerationSignalButSlow)
            ) {
                earlyOcrAttempted = true
                // Learned COPY is cheaper and more exact than OCR when a provider hides
                // assistant text from Accessibility. Bounded scrolling handles a long reply.
                tryLearnedCopyResponse(run, provider, requestId) { fromCopy ->
                    if (!alive(run)) return@tryLearnedCopyResponse
                    if (fromCopy != null) {
                        waitingForAi = false
                        callback(fromCopy)
                    } else {
                        captureProviderOcr(provider) { ocr ->
                            if (!alive(run)) return@captureProviderOcr
                            val fromOcr = parseCommand(ocr, requestId)
                            if (fromOcr != null) {
                                waitingForAi = false
                                callback(fromOcr)
                            } else {
                                handler.postDelayed({ if (alive(run)) poll() }, 320L)
                            }
                        }
                    }
                }
                return
            }
'''
    s = replace_once(s, old_ocr, new_ocr, 'learned copy before OCR')

    # Strengthen compact machine-only contract without changing the existing parser.
    contract_old = '''                appendLine("OUTPUT CONTRACT:")
                appendLine("AARIS::<request-id>::<ACTION>::<ELEMENT>::<PAYLOAD>::<EXPECTED>::<VISUAL>::END")
'''
    contract_new = '''                appendLine("OUTPUT CONTRACT:")
                appendLine("Return exactly ONE compact machine line only. No markdown, prose, explanation, headings, or extra lines.")
                appendLine("AARIS::<request-id>::<ACTION>::<ELEMENT>::<PAYLOAD>::<EXPECTED>::<VISUAL>::END")
'''
    if contract_old in s:
        s = s.replace(contract_old, contract_new, 1)

    SIDE.write_text(s, encoding='utf-8')

# Basic static invariants before Gradle gets a turn.
for path in (AUTO, FCS, SIDE):
    text = path.read_text(encoding='utf-8')
    if text.count('{') < text.count('}') - 2 or text.count('}') < text.count('{') - 2:
        raise SystemExit(f'brace sanity failed for {path}')

print('AARISH_UNIVERSAL_AI_TEACH_RELAY_V3_PATCHED')
