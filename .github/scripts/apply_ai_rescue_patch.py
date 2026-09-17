from pathlib import Path
import re

ROOT = Path('.')
FCS = ROOT / 'app/src/main/java/com/aarishkhan/aarishai/FloatingControlService.kt'
AAS = ROOT / 'app/src/main/java/com/aarishkhan/aarishai/AutoActionService.kt'
AI = ROOT / 'app/src/main/java/com/aarishkhan/aarishai/AiSidecarController.kt'
GS = ROOT / 'app/src/main/java/com/aarishkhan/aarishai/GestureStore.kt'


def fail(message: str):
    raise SystemExit(message)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        fail(f'{label}: anchor not found')
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# GestureStore: backward-compatible path to a recording-time evidence image.
# ---------------------------------------------------------------------------
gs = GS.read_text(encoding='utf-8')
if 'val recordingEvidencePath: String? = null' not in gs:
    start = gs.find('data class RecordedGesture(')
    end = gs.find('\n)\n\nobject GestureStore', start)
    if start < 0 or end < 0:
        fail('GestureStore: RecordedGesture bounds not found')
    block = gs[start:end + 2]
    old_tail = '''    val recordedScreenW: Int = 0,
    val recordedScreenH: Int = 0,
)'''
    new_tail = '''    val recordedScreenW: Int = 0,
    val recordedScreenH: Int = 0,
    val recordingEvidencePath: String? = null,
)'''
    if old_tail not in block:
        fail('GestureStore: RecordedGesture tail not found')
    block = block.replace(old_tail, new_tail, 1)
    gs = gs[:start] + block + gs[end + 2:]

if 'gestureObject.put("recordingEvidencePath"' not in gs:
    gs = replace_once(
        gs,
        '            gestureObject.put("recordedScreenH", gesture.recordedScreenH.coerceAtLeast(0))\n',
        '            gestureObject.put("recordedScreenH", gesture.recordedScreenH.coerceAtLeast(0))\n'
        '            gestureObject.put("recordingEvidencePath", gesture.recordingEvidencePath.orEmpty())\n',
        'GestureStore save evidence path'
    )

if 'recordingEvidencePath = cleanOpt(gestureObject, "recordingEvidencePath")' not in gs:
    gs = replace_once(
        gs,
        '                        recordedScreenH = gestureObject.optInt("recordedScreenH", 0).coerceAtLeast(0)\n',
        '                        recordedScreenH = gestureObject.optInt("recordedScreenH", 0).coerceAtLeast(0),\n'
        '                        recordingEvidencePath = cleanOpt(gestureObject, "recordingEvidencePath")\n',
        'GestureStore load evidence path'
    )
GS.write_text(gs, encoding='utf-8')


# ---------------------------------------------------------------------------
# AutoActionService: capture evidence, stop blind semantic XY fallback,
# and provide recent recorded context to the AI rescue controller.
# ---------------------------------------------------------------------------
aas = AAS.read_text(encoding='utf-8')

if 'fun captureRecordingEvidenceSnapshot(' not in aas:
    anchor = '''        fun captureTargetSnapshot(
            x: Int,
            y: Int,
            screenW: Float,
            screenH: Float
        ): TargetSnapshot? {
            return instance?.captureTargetSnapshotInternal(x, y, screenW, screenH)
        }
'''
    addition = anchor + '''
        // AARISH_RECORDING_EVIDENCE_V1: one screenshot feeds both OCR and durable replay evidence.
        fun captureRecordingEvidenceSnapshot(
            x: Int,
            y: Int,
            screenW: Float,
            screenH: Float,
            callback: (TargetSnapshot?, String?) -> Unit
        ): Boolean {
            val service = instance ?: return false
            android.os.Handler(android.os.Looper.getMainLooper()).post {
                service.aarishCaptureRecordingEvidenceSnapshotInternal(x, y, screenW, screenH, callback)
            }
            return true
        }
'''
    aas = replace_once(aas, anchor, addition, 'AAS evidence bridge')

if 'private var aarishReplayContextSteps: List<RecordedGesture>' not in aas:
    aas = replace_once(
        aas,
        '    private var isMasterPlaybackInternal = false\n',
        '    private var isMasterPlaybackInternal = false\n'
        '    // AARISH_AI_RESCUE_CONTEXT_V2\n'
        '    private var aarishReplayContextSteps: List<RecordedGesture> = emptyList()\n',
        'AAS replay context field'
    )

if 'AARISH_RECORDING_EVIDENCE_V1_SAVE' not in aas:
    marker = '    private fun aarishOcrBoxesFromResult(result: com.google.mlkit.vision.text.Text): List<AarishOcrBox> {'
    pos = aas.find(marker)
    if pos < 0:
        fail('AAS evidence helper insertion marker missing')
    helper = r'''    // AARISH_RECORDING_EVIDENCE_V1_SAVE
    private fun aarishSaveRecordingEvidenceBitmap(
        source: android.graphics.Bitmap,
        tapX: Int,
        tapY: Int
    ): String? {
        return try {
            val srcW = source.width.coerceAtLeast(1)
            val srcH = source.height.coerceAtLeast(1)
            val maxW = 720
            val scale = kotlin.math.min(1f, maxW.toFloat() / srcW.toFloat())
            val outW = (srcW * scale).toInt().coerceAtLeast(1)
            val outH = (srcH * scale).toInt().coerceAtLeast(1)
            val scaled = if (outW == srcW && outH == srcH) {
                source.copy(android.graphics.Bitmap.Config.ARGB_8888, true)
            } else {
                android.graphics.Bitmap.createScaledBitmap(source, outW, outH, true)
                    .copy(android.graphics.Bitmap.Config.ARGB_8888, true)
            }

            val sx = outW.toFloat() / srcW.toFloat()
            val sy = outH.toFloat() / srcH.toFloat()
            val cx = (tapX * sx).coerceIn(0f, (outW - 1).toFloat().coerceAtLeast(0f))
            val cy = (tapY * sy).coerceIn(0f, (outH - 1).toFloat().coerceAtLeast(0f))
            val density = resources.displayMetrics.density.coerceAtLeast(1f)
            val canvas = android.graphics.Canvas(scaled)
            val ring = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
                style = android.graphics.Paint.Style.STROKE
                strokeWidth = (4f * density).coerceAtLeast(4f)
                color = android.graphics.Color.RED
            }
            val cross = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
                style = android.graphics.Paint.Style.STROKE
                strokeWidth = (2.4f * density).coerceAtLeast(2.4f)
                color = android.graphics.Color.YELLOW
            }
            val radius = (22f * density).coerceIn(18f, 44f)
            canvas.drawCircle(cx, cy, radius, ring)
            canvas.drawLine(cx - radius, cy, cx + radius, cy, cross)
            canvas.drawLine(cx, cy - radius, cx, cy + radius, cross)

            val dir = java.io.File(filesDir, "aarish_recording_evidence").apply { mkdirs() }
            val file = java.io.File(dir, "step_${System.currentTimeMillis()}_${java.util.UUID.randomUUID()}.jpg")
            java.io.FileOutputStream(file).use { stream ->
                scaled.compress(android.graphics.Bitmap.CompressFormat.JPEG, 72, stream)
            }

            // Bound private evidence storage so long-term recording use cannot grow forever.
            try {
                dir.listFiles()
                    ?.filter { it.isFile && it.name.startsWith("step_") }
                    ?.sortedByDescending { it.lastModified() }
                    ?.drop(180)
                    ?.forEach { it.delete() }
            } catch (_: Throwable) {}

            try { scaled.recycle() } catch (_: Throwable) {}
            file.absolutePath
        } catch (_: Throwable) {
            null
        }
    }

    // AARISH_RECORDING_EVIDENCE_V1_CAPTURE
    private fun aarishCaptureRecordingEvidenceSnapshotInternal(
        x: Int,
        y: Int,
        screenW: Float,
        screenH: Float,
        callback: (TargetSnapshot?, String?) -> Unit
    ) {
        if (android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.R) {
            callback(null, null)
            return
        }

        val executor = java.util.concurrent.Executor { runnable -> handler.post(runnable) }
        val delivered = java.util.concurrent.atomic.AtomicBoolean(false)
        var timeoutTask: Runnable? = null

        fun finish(snapshot: TargetSnapshot?, evidencePath: String?) {
            if (!delivered.compareAndSet(false, true)) return
            try { timeoutTask?.let { handler.removeCallbacks(it) } } catch (_: Throwable) {}
            callback(snapshot, evidencePath)
        }

        timeoutTask = Runnable { finish(null, null) }
        handler.postDelayed(timeoutTask!!, 8500L)

        try {
            takeScreenshot(
                android.view.Display.DEFAULT_DISPLAY,
                executor,
                object : android.accessibilityservice.AccessibilityService.TakeScreenshotCallback {
                    override fun onSuccess(
                        screenshot: android.accessibilityservice.AccessibilityService.ScreenshotResult
                    ) {
                        val bitmap = aarishBitmapFromScreenshot(screenshot)
                        if (bitmap == null) {
                            finish(null, null)
                            return
                        }

                        // Save the user's recording-time view before the app can change screens.
                        val evidencePath = aarishSaveRecordingEvidenceBitmap(bitmap, x, y)
                        aarishProcessOcrBoxesFromBitmapV29(
                            bitmap = bitmap,
                            onSuccess = { boxes ->
                                val picked = aarishPickOcrBoxForTap(boxes, x, y, screenW, screenH)
                                val snapshot = picked?.let {
                                    aarishMakeOcrSnapshotFromBox(it, x, y, screenW, screenH, boxes)
                                }
                                finish(snapshot, evidencePath)
                                try { bitmap.recycle() } catch (_: Throwable) {}
                            },
                            onFailure = {
                                finish(null, evidencePath)
                                try { bitmap.recycle() } catch (_: Throwable) {}
                            }
                        )
                    }

                    override fun onFailure(errorCode: Int) {
                        finish(null, null)
                    }
                }
            )
        } catch (_: Throwable) {
            finish(null, null)
        }
    }

'''
    aas = aas[:pos] + helper + aas[pos:]

if 'AARISH_AI_RESCUE_CONTEXT_V2_CAPTURE' not in aas:
    aas = replace_once(
        aas,
        '                    dispatchOneGesture(gesture, runId, nextRealGestureAfter(index))\n',
        '''                    // AARISH_AI_RESCUE_CONTEXT_V2_CAPTURE
                    aarishReplayContextSteps = orderedGestures
                        .take(index + 1)
                        .filter { (it.points.firstOrNull()?.x ?: -999f) > -50f }
                        .takeLast(4)
                    dispatchOneGesture(gesture, runId, nextRealGestureAfter(index))
''',
        'AAS replay context capture'
    )

# OCR target missing: do not silently tap the old coordinate; enter the same bounded rescue path.
if 'AARISH_OCR_MISS_TO_AI_RESCUE_V2' not in aas:
    pattern = re.compile(
        r'    private fun aarishFallbackTapForOcrMiss\(g: RecordedGesture, runId: Int, token: Int\) \{.*?\n    \}\n\n\n\n    private fun tryOcrTextTargetTap',
        re.S,
    )
    replacement = '''    private fun aarishFallbackTapForOcrMiss(g: RecordedGesture, runId: Int, token: Int) {
        // AARISH_OCR_MISS_TO_AI_RESCUE_V2
        if (!isCurrentCallbackRun(runId)) return
        finishActiveGesture(token)
        val started = try {
            trySmartTargetAfterShortSettle(g, runId, 3500L)
        } catch (_: Throwable) {
            false
        }
        if (!started && isSamePlaybackRun(runId)) {
            showTinyToast("Target nahi mila — AI rescue unavailable")
            stopPlaybackInternal(showToast = false)
        }
    }



    private fun tryOcrTextTargetTap'''
    aas, count = pattern.subn(replacement, aas, count=1)
    if count != 1:
        fail(f'AAS OCR fallback replacement count={count}')

if 'AARISH_AI_RESCUE_ALWAYS_ON_SEMANTIC_MISS_V2' not in aas:
    old = '''        if (!movement && match == null &&
            (hasStrongSavedIdentity(recordedGesture) || hasSavedPercentAnchor(recordedGesture) || aarishHasAnyRichIdentity(recordedGesture))
        ) {
            if (trySmartTargetAfterShortSettle(recordedGesture, runId)) return
        }
'''
    new = '''        if (!movement &&
            (hasStrongSavedIdentity(recordedGesture) || hasSavedPercentAnchor(recordedGesture) || aarishHasAnyRichIdentity(recordedGesture))
        ) {
            // AARISH_AI_RESCUE_ALWAYS_ON_SEMANTIC_MISS_V2
            if (trySmartTargetAfterShortSettle(recordedGesture, runId, 3500L)) return
        }
'''
    aas = replace_once(aas, old, new, 'AAS semantic miss rescue gate')

aas = aas.replace('        waitMs: Long = 10_000L\n', '        waitMs: Long = 3_500L\n', 1)

if 'AARISH_SEMANTIC_RETRY_FAIL_CLOSED_V2' not in aas:
    old = '''            if (!movement && duration < 450L) {
                if (performSmartNodeClick(retryMatch, recordedGesture, runId)) return true
                performGestureAt(startX, startY, orderedPoints, runId, recordedGesture)
                return true
            }
'''
    new = '''            if (!movement && duration < 450L) {
                // AARISH_SEMANTIC_RETRY_FAIL_CLOSED_V2
                return performSmartNodeClick(retryMatch, recordedGesture, runId)
            }
'''
    aas = replace_once(aas, old, new, 'AAS semantic retry fail closed')

if 'rescueRecordedFailure(recordedGesture, aarishReplayContextSteps)' not in aas:
    aas = replace_once(
        aas,
        '                        aiSidecarController.rescueRecordedFailure(recordedGesture) { ok ->\n',
        '                        aiSidecarController.rescueRecordedFailure(recordedGesture, aarishReplayContextSteps) { ok ->\n',
        'AAS rescue context call'
    )

# A primary text/id/description identity must not degrade into “same shape at old position”.
if 'aarishGeometryFallbackWhenIdentityMissing' not in aas:
    marker = 'private fun findBestSmartTarget(gesture: RecordedGesture): SmartMatch? {'
    pos = aas.find(marker)
    if pos < 0:
        fail('AAS findBestSmartTarget marker missing')
    helper = '''private fun aarishGeometryFallbackWhenIdentityMissing(gesture: RecordedGesture): SmartMatch? {
        // AARISH_IDENTITY_NO_BLIND_GEOMETRY_V2
        return if (aarishHasPrimaryIdentity(gesture)) null else findGeometrySmartTarget(gesture)
    }

'''
    aas = aas[:pos] + helper + aas[pos:]
    start = aas.find(marker, pos + len(helper))
    end = aas.find('    // AARISH_AI_SMART_CLICK_V6_HELPERS', start)
    if start < 0 or end < 0:
        fail('AAS smart-target block bounds missing')
    block = aas[start:end].replace(
        'findGeometrySmartTarget(gesture)',
        'aarishGeometryFallbackWhenIdentityMissing(gesture)'
    )
    aas = aas[:start] + block + aas[end:]

# Cleanup context when playback stops/completes. These are best-effort idempotent inserts.
if 'AARISH_AI_RESCUE_CONTEXT_V2_STOP' not in aas:
    anchor = '    resetActiveGestures()\n    chainVisitedInRun.clear()\n'
    if anchor in aas:
        aas = aas.replace(
            anchor,
            '    resetActiveGestures()\n'
            '    aarishReplayContextSteps = emptyList() // AARISH_AI_RESCUE_CONTEXT_V2_STOP\n'
            '    chainVisitedInRun.clear()\n',
            1
        )
AAS.write_text(aas, encoding='utf-8')


# ---------------------------------------------------------------------------
# FloatingControlService: permanent 🤖 immediately right of 📱 and attach
# recording evidence path from the unified OCR/screenshot capture.
# ---------------------------------------------------------------------------
fcs = FCS.read_text(encoding='utf-8')

if 'AARISH_AI_AGENT_BOTTOM_ROW_V2' not in fcs:
    marker = '    // Future buttons yahin bottomRow me add honge. AARISH_PANEL_PERMANENT_TWO_ROWS_V13_FUTURE_SLOT'
    block = '''    // AARISH_AI_AGENT_BOTTOM_ROW_V2: permanent autonomous-agent button immediately right of phone launcher.
    if (::btnAgent.isInitialized) {
        btnAgent.text = "🤖"
        btnAgent.contentDescription = "Autonomous AI Mission"
        btnAgent.visibility = if (!AutoActionService.isPlaying()) View.VISIBLE else View.GONE
        try { stylePanelButton(btnAgent, Color.rgb(124, 58, 237), Color.WHITE, 34) } catch (_: Throwable) {}
        addPanelChildKeepSizeV13(bottomRow, btnAgent)
    }

    // Future buttons yahin bottomRow me add honge. AARISH_PANEL_PERMANENT_TWO_ROWS_V13_FUTURE_SLOT'''
    fcs = replace_once(fcs, marker, block, 'FCS AI button bottom row')

if 'private var recordingEvidencePrefetchPath: String?' not in fcs:
    fcs = replace_once(
        fcs,
        '    private var ocrPendingGestureSerial = 0\n',
        '    private var ocrPendingGestureSerial = 0\n'
        '    // AARISH_RECORDING_EVIDENCE_V1\n'
        '    private var recordingEvidencePrefetchPath: String? = null\n',
        'FCS evidence field'
    )

if 'captureRecordingEvidenceSnapshot(x, y, screenW, screenH)' not in fcs:
    fcs = replace_once(
        fcs,
        '        val started = AutoActionService.captureOcrTextSnapshot(x, y, screenW, screenH) { ocrSnapshot ->\n',
        '        val started = AutoActionService.captureRecordingEvidenceSnapshot(x, y, screenW, screenH) { ocrSnapshot, evidencePath ->\n',
        'FCS unified capture call'
    )

if 'recordingEvidencePrefetchPath = evidencePath ?: recordingEvidencePrefetchPath' not in fcs:
    old = '''                if (isActiveTap) {
                    ocrSavePending = false
                    if (ocrSnapshot != null) {
                        ocrPrefetchSnapshot = ocrSnapshot
                    }
                }
'''
    new = '''                if (isActiveTap) {
                    ocrSavePending = false
                    recordingEvidencePrefetchPath = evidencePath ?: recordingEvidencePrefetchPath
                    if (ocrSnapshot != null) {
                        ocrPrefetchSnapshot = ocrSnapshot
                    }
                }
'''
    fcs = replace_once(fcs, old, new, 'FCS active evidence callback')

if 'val merged = if (ocrSnapshot != null) applyOcrSnapshotToGestureV5(old, ocrSnapshot) else old' not in fcs:
    old = '''                if (isPendingSavedGesture) {
                    if (ocrSnapshot != null) {
                        val idx = ocrPendingGestureIndex
                        val old = recordedGestures.getOrNull(idx)
                        if (old != null) {
                            recordedGestures[idx] = applyOcrSnapshotToGestureV5(old, ocrSnapshot)
                            aarishTraceTextToast(aarishTraceOcrLabel(ocrSnapshot.targetText))
                        }
                    }
                    clearOcrPendingGestureV5(serial)
                }
'''
    new = '''                if (isPendingSavedGesture) {
                    val idx = ocrPendingGestureIndex
                    val old = recordedGestures.getOrNull(idx)
                    if (old != null) {
                        val merged = if (ocrSnapshot != null) applyOcrSnapshotToGestureV5(old, ocrSnapshot) else old
                        recordedGestures[idx] = merged.copy(
                            recordingEvidencePath = evidencePath ?: merged.recordingEvidencePath
                        )
                        if (ocrSnapshot != null) aarishTraceTextToast(aarishTraceOcrLabel(ocrSnapshot.targetText))
                    }
                    clearOcrPendingGestureV5(serial)
                }
'''
    fcs = replace_once(fcs, old, new, 'FCS pending evidence callback')

if 'recordingEvidencePrefetchPath = null // AARISH_RECORDING_EVIDENCE_V1_NEW_TAP' not in fcs:
    fcs = replace_once(
        fcs,
        '        ocrSaveSerial++\n        val serial = ocrSaveSerial\n',
        '        recordingEvidencePrefetchPath = null // AARISH_RECORDING_EVIDENCE_V1_NEW_TAP\n'
        '        ocrSaveSerial++\n'
        '        val serial = ocrSaveSerial\n',
        'FCS evidence reset'
    )

if 'recordingEvidencePath = if (forceXyOnly) null else recordingEvidencePrefetchPath' not in fcs:
    fcs = replace_once(
        fcs,
        '''            recordedScreenW = snapshot?.recordedScreenW ?: metrics.widthPixels,
            recordedScreenH = snapshot?.recordedScreenH ?: metrics.heightPixels
        )
''',
        '''            recordedScreenW = snapshot?.recordedScreenW ?: metrics.widthPixels,
            recordedScreenH = snapshot?.recordedScreenH ?: metrics.heightPixels,
            recordingEvidencePath = if (forceXyOnly) null else recordingEvidencePrefetchPath
        )
''',
        'FCS RecordedGesture evidence constructor'
    )

if 'recordingEvidencePrefetchPath = null // AARISH_RECORDING_EVIDENCE_V1_AFTER_SAVE' not in fcs:
    fcs = replace_once(
        fcs,
        '''        recordedGestures.add(finalGesture)
        if (!forceXyOnly) rememberPendingOcrForLastSavedGestureV5(finalGesture)

        // Tap, double tap, swipe, long press sab raw gesture ke form me live replay hoga.
''',
        '''        recordedGestures.add(finalGesture)
        if (!forceXyOnly) rememberPendingOcrForLastSavedGestureV5(finalGesture)
        recordingEvidencePrefetchPath = null // AARISH_RECORDING_EVIDENCE_V1_AFTER_SAVE

        // Tap, double tap, swipe, long press sab raw gesture ke form me live replay hoga.
''',
        'FCS evidence clear after save'
    )
FCS.write_text(fcs, encoding='utf-8')


# ---------------------------------------------------------------------------
# AiSidecarController: provider isolation, evidence grid, target AI apps allowed,
# and horizontal recovery for launcher pages/carousels.
# ---------------------------------------------------------------------------
ai = AI.read_text(encoding='utf-8')

if 'private var rescueEvidenceSteps: List<RecordedGesture>' not in ai:
    ai = replace_once(
        ai,
        '    private var rescueExpectedAction = ""\n',
        '    private var rescueExpectedAction = ""\n'
        '    // AARISH_AI_RESCUE_EVIDENCE_V2\n'
        '    private var rescueEvidenceSteps: List<RecordedGesture> = emptyList()\n',
        'AI rescue evidence field'
    )

if 'contextSteps: List<RecordedGesture> = emptyList()' not in ai:
    ai = replace_once(
        ai,
        '    fun rescueRecordedFailure(gesture: RecordedGesture, callback: (Boolean) -> Unit): Boolean {\n',
        '''    fun rescueRecordedFailure(
        gesture: RecordedGesture,
        contextSteps: List<RecordedGesture> = emptyList(),
        callback: (Boolean) -> Unit
    ): Boolean {
''',
        'AI rescue signature'
    )

if 'AARISH_AI_RESCUE_CONTEXT_SUMMARY_V2' not in ai:
    ai = replace_once(
        ai,
        '''        rescueExpectedAction = inferRecordedAction(gesture)

        missionGoal = buildString {
''',
        '''        rescueExpectedAction = inferRecordedAction(gesture)
        rescueEvidenceSteps = (contextSteps + gesture)
            .distinctBy { g ->
                listOf(g.delayFromStart.toString(), g.targetId.orEmpty(), g.targetText.orEmpty(), g.targetDesc.orEmpty()).joinToString("|")
            }
            .takeLast(4)
        val recordedContextSummary = rescueEvidenceSteps.mapIndexed { index, g ->
            val action = inferRecordedAction(g)
            val label = listOfNotNull(g.targetText, g.targetDesc, g.targetId?.substringAfterLast('/'))
                .filter { it.isNotBlank() }
                .distinct()
                .joinToString(" / ")
                .take(220)
            val ctx = g.targetContextText.orEmpty().replace(Regex("\\s+"), " ").trim().take(220)
            "Recorded context ${index + 1}: action=$action package=${g.targetPackage.orEmpty()} target=${label.ifBlank { "unknown" }} x=${g.xPercent} y=${g.yPercent} context=$ctx"
        }.joinToString(" || ")

        missionGoal = buildString {
''',
        'AI recorded context summary'
    )
    ai = replace_once(
        ai,
        '''            append("Recorded target: ")
            append(target.ifBlank { "unknown target" })
        }
''',
        '''            append("Recorded target: ")
            append(target.ifBlank { "unknown target" })
            append(". AARISH_AI_RESCUE_CONTEXT_SUMMARY_V2: ")
            append(recordedContextSummary.take(3200))
            append(". The attached rescue evidence may show prior RECORDED steps with marked click points plus the CURRENT screen. Recover ONLY the missing recorded step; do not repeat already-completed steps.")
        }
''',
        'AI rescue goal evidence text'
    )

if 'rescueEvidenceSteps = emptyList() // AARISH_AI_RESCUE_EVIDENCE_V2_START_CLEAR' not in ai:
    ai = replace_once(
        ai,
        '        rescueExpectedAction = ""\n        missionGoal = clean\n',
        '        rescueExpectedAction = ""\n'
        '        rescueEvidenceSteps = emptyList() // AARISH_AI_RESCUE_EVIDENCE_V2_START_CLEAR\n'
        '        missionGoal = clean\n',
        'AI normal mission evidence clear'
    )

if 'selectProvider(state.packageName)' not in ai:
    ai = replace_once(ai, '            val provider = selectProvider()\n', '            val provider = selectProvider(state.packageName)\n', 'AI provider call')

if 'private fun selectProvider(targetPackage: String = "")' not in ai:
    pattern = re.compile(
        r'    private fun selectProvider\(\): Provider\? \{.*?\n    \}\n\n    private fun buildPlannerPrompt',
        re.S,
    )
    replacement = '''    private fun selectProvider(targetPackage: String = ""): Provider? {
        val installed = Provider.values().filter(::providerInstalled)
        if (installed.isEmpty()) return null

        // AARISH_PROVIDER_SELF_TARGET_GUARD_V2
        val candidates = installed.filterNot {
            targetPackage.isNotBlank() && it.packageName == targetPackage
        }
        if (candidates.isEmpty()) return null

        when (providerPreference) {
            "CHATGPT" -> Provider.CHATGPT.takeIf { it in candidates }?.let { return it }
            "GEMINI" -> Provider.GEMINI.takeIf { it in candidates }?.let { return it }
        }

        val now = SystemClock.elapsedRealtime()
        val ready = candidates.filter { (providerCooldownUntil[it] ?: 0L) <= now }
        if (ready.isNotEmpty()) {
            return ready.minWithOrNull(
                compareBy<Provider>(
                    { providerFailureStreak[it] ?: 0 },
                    { if (it == lastProviderAttempt) 0 else 1 },
                    { it.ordinal }
                )
            )
        }
        return candidates.minByOrNull { providerCooldownUntil[it] ?: Long.MAX_VALUE }
    }

    private fun buildPlannerPrompt'''
    ai, count = pattern.subn(replacement, ai, count=1)
    if count != 1:
        fail(f'AI selectProvider replacement count={count}')

if 'val targetAi = Provider.values().firstOrNull { it.packageName == state.packageName }' not in ai:
    ai = replace_once(
        ai,
        '''            if (provider == null) {
                finishMission(false, "ChatGPT/Gemini installed nahi mila")
                return@captureTargetScreen
            }
''',
        '''            if (provider == null) {
                val targetAi = Provider.values().firstOrNull { it.packageName == state.packageName }
                finishMission(
                    false,
                    if (targetAi != null) "Target app ${targetAi.name} hai; agent brain ke liye doosra AI install/select karo" else "ChatGPT/Gemini installed nahi mila"
                )
                return@captureTargetScreen
            }
''',
        'AI provider-null message'
    )

if 'AARISH_AI_RESCUE_EVIDENCE_GRID_V2' not in ai:
    marker = '    private fun askPhysicalAi(\n'
    pos = ai.find(marker)
    if pos < 0:
        fail('AI askPhysicalAi insertion marker missing')
    helper = r'''    // AARISH_AI_RESCUE_EVIDENCE_GRID_V2
    private fun buildRescueEvidenceAttachment(currentScreenshot: File?): File? {
        val recent = rescueEvidenceSteps.takeLast(3)
        val items = mutableListOf<Pair<String, File>>()
        recent.forEachIndexed { index, g ->
            val path = g.recordingEvidencePath.orEmpty()
            if (path.isNotBlank()) {
                val file = File(path)
                if (file.exists() && file.isFile) {
                    val label = if (index == recent.lastIndex) "FAILED RECORDED STEP" else "RECORDED CONTEXT ${index + 1}"
                    items.add(label to file)
                }
            }
        }
        if (currentScreenshot != null && currentScreenshot.exists()) {
            items.add("CURRENT SCREEN" to currentScreenshot)
        }
        if (items.isEmpty()) return currentScreenshot
        if (items.size == 1 && items.first().second == currentScreenshot) return currentScreenshot

        val decoded = items.mapNotNull { item ->
            try {
                android.graphics.BitmapFactory.decodeFile(item.second.absolutePath)?.let { item.first to it }
            } catch (_: Throwable) { null }
        }.take(4)
        if (decoded.isEmpty()) return currentScreenshot

        return try {
            val cellW = 480
            val cellH = 900
            val labelH = 54
            val cols = 2
            val rows = ((decoded.size + cols - 1) / cols).coerceAtLeast(1)
            val output = Bitmap.createBitmap(cellW * cols, cellH * rows, Bitmap.Config.ARGB_8888)
            val canvas = Canvas(output)
            canvas.drawColor(Color.rgb(18, 18, 18))
            val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = Color.WHITE
                textSize = 25f
                typeface = Typeface.DEFAULT_BOLD
            }
            val borderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = Color.rgb(90, 90, 90)
                style = Paint.Style.STROKE
                strokeWidth = 2f
            }

            decoded.forEachIndexed { i, pair ->
                val col = i % cols
                val row = i / cols
                val left = col * cellW
                val top = row * cellH
                canvas.drawText(pair.first.take(28), left + 12f, top + 35f, labelPaint)
                val src = pair.second
                val availW = (cellW - 20).coerceAtLeast(1)
                val availH = (cellH - labelH - 20).coerceAtLeast(1)
                val scale = minOf(
                    availW.toFloat() / src.width.coerceAtLeast(1),
                    availH.toFloat() / src.height.coerceAtLeast(1)
                )
                val width = (src.width * scale).toInt().coerceAtLeast(1)
                val height = (src.height * scale).toInt().coerceAtLeast(1)
                val dstLeft = left + (cellW - width) / 2
                val dstTop = top + labelH + (availH - height) / 2
                val dst = Rect(dstLeft, dstTop, dstLeft + width, dstTop + height)
                canvas.drawBitmap(src, null, dst, null)
                canvas.drawRect(left.toFloat(), top.toFloat(), (left + cellW - 1).toFloat(), (top + cellH - 1).toFloat(), borderPaint)
            }

            val dir = File(service.cacheDir, "ai_sidecar").apply { mkdirs() }
            val file = File(dir, "rescue_${UUID.randomUUID()}.png")
            FileOutputStream(file).use { stream ->
                output.compress(Bitmap.CompressFormat.PNG, 92, stream)
            }
            decoded.forEach { try { it.second.recycle() } catch (_: Throwable) {} }
            try { output.recycle() } catch (_: Throwable) {}
            file
        } catch (_: Throwable) {
            decoded.forEach { try { it.second.recycle() } catch (_: Throwable) {} }
            currentScreenshot
        }
    }

'''
    ai = ai[:pos] + helper + ai[pos:]

if 'val aiAttachment = if (rescueMode)' not in ai:
    ai = replace_once(
        ai,
        '            askPhysicalAi(run, provider, requestId, prompt, state.screenshot) { command ->\n',
        '            val aiAttachment = if (rescueMode) buildRescueEvidenceAttachment(state.screenshot) else state.screenshot\n'
        '            askPhysicalAi(run, provider, requestId, prompt, aiAttachment) { command ->\n',
        'AI evidence attachment call'
    )

if 'AARISH_AI_APP_CAN_BE_TARGET_V2' not in ai:
    ai = replace_once(
        ai,
        '        val forbidden = setOf(service.packageName, Provider.CHATGPT.packageName, Provider.GEMINI.packageName)\n',
        '        val forbidden = setOf(service.packageName) // AARISH_AI_APP_CAN_BE_TARGET_V2\n',
        'AI target root allow AI apps'
    )

ai = ai.replace('SCROLL (UP/DOWN)', 'SCROLL (UP/DOWN/LEFT/RIGHT)')
ai = ai.replace('intermediate BACK, OPEN_APP, SCROLL or WAIT', 'intermediate BACK, OPEN_APP, SCROLL (including LEFT/RIGHT) or WAIT')

if 'private fun performDirectionalSwipe(' not in ai:
    marker = '    private fun executeCommand(run: Int, command: AiCommand, state: ScreenState, callback: (Boolean, String) -> Unit) {'
    pos = ai.find(marker)
    if pos < 0:
        fail('AI executeCommand insertion marker missing')
    helper = '''    private fun performDirectionalSwipe(directionRaw: String): Boolean {
        if (Build.VERSION.SDK_INT < 24) return false
        val direction = directionRaw.trim().uppercase(Locale.US)
        val width = service.resources.displayMetrics.widthPixels.toFloat().coerceAtLeast(2f)
        val height = service.resources.displayMetrics.heightPixels.toFloat().coerceAtLeast(2f)
        val cx = width * 0.50f
        val cy = height * 0.52f
        val path = Path()
        when {
            direction.contains("LEFT") -> { path.moveTo(width * 0.78f, cy); path.lineTo(width * 0.22f, cy) }
            direction.contains("RIGHT") -> { path.moveTo(width * 0.22f, cy); path.lineTo(width * 0.78f, cy) }
            direction.contains("UP") || direction.contains("BACK") -> { path.moveTo(cx, height * 0.72f); path.lineTo(cx, height * 0.28f) }
            else -> { path.moveTo(cx, height * 0.28f); path.lineTo(cx, height * 0.72f) }
        }
        return try {
            val gesture = GestureDescription.Builder()
                .addStroke(GestureDescription.StrokeDescription(path, 0L, 430L))
                .build()
            service.dispatchGesture(gesture, null, null)
        } catch (_: Throwable) { false }
    }

'''
    ai = ai[:pos] + helper + ai[pos:]

if 'callback(performDirectionalSwipe(direction), "Swiped $direction")' not in ai:
    old = '''            "SCROLL" -> {
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
'''
    new = '''            "SCROLL" -> {
                val direction = command.payload.trim().uppercase(Locale.US)
                if (direction.contains("LEFT") || direction.contains("RIGHT")) {
                    callback(performDirectionalSwipe(direction), "Swiped $direction")
                } else {
                    val saved = state.elements.firstOrNull { it.key.equals(command.elementKey, true) }
                    val live = saved?.let { findBestLiveMatch(it) } ?: findScrollableNode()
                    val nodeAction = if (direction.contains("UP") || direction.contains("BACK"))
                        AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
                    else AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
                    val nodeOk = if (live != null) try { live.performAction(nodeAction) } catch (_: Throwable) { false } else false
                    val ok = nodeOk || performDirectionalSwipe(direction)
                    callback(ok, "Scrolled $direction")
                }
            }
'''
    ai = replace_once(ai, old, new, 'AI scroll directions')

AI.write_text(ai, encoding='utf-8')


# Final static assertions: fail before touching main if an expected feature is absent.
checks = {
    'GestureStore evidence path': 'recordingEvidencePath' in GS.read_text(encoding='utf-8'),
    'Agent button bottom row': 'addPanelChildKeepSizeV13(bottomRow, btnAgent)' in FCS.read_text(encoding='utf-8'),
    'Unified recording evidence capture': 'captureRecordingEvidenceSnapshot' in FCS.read_text(encoding='utf-8'),
    'Evidence screenshot saver': 'AARISH_RECORDING_EVIDENCE_V1_SAVE' in AAS.read_text(encoding='utf-8'),
    'Semantic misses enter rescue': 'AARISH_AI_RESCUE_ALWAYS_ON_SEMANTIC_MISS_V2' in AAS.read_text(encoding='utf-8'),
    'No blind identity geometry': 'AARISH_IDENTITY_NO_BLIND_GEOMETRY_V2' in AAS.read_text(encoding='utf-8'),
    'Replay context reaches sidecar': 'rescueRecordedFailure(recordedGesture, aarishReplayContextSteps)' in AAS.read_text(encoding='utf-8'),
    'AI evidence grid': 'AARISH_AI_RESCUE_EVIDENCE_GRID_V2' in AI.read_text(encoding='utf-8'),
    'Provider self-target guard': 'AARISH_PROVIDER_SELF_TARGET_GUARD_V2' in AI.read_text(encoding='utf-8'),
    'AI apps can be targets': 'AARISH_AI_APP_CAN_BE_TARGET_V2' in AI.read_text(encoding='utf-8'),
    'Horizontal AI recovery': 'performDirectionalSwipe' in AI.read_text(encoding='utf-8'),
}
missing = [name for name, ok in checks.items() if not ok]
if missing:
    fail('Static assertions failed: ' + ', '.join(missing))

print('AI rescue patch applied; static assertions passed.')
