from pathlib import Path

sidecar = Path('app/src/main/java/com/aarishkhan/aarishai/AiSidecarController.kt')
floating = Path('app/src/main/java/com/aarishkhan/aarishai/FloatingControlService.kt')

s = sidecar.read_text(encoding='utf-8')

# Centralize volatile mission state cleanup so DONE/FAIL/rescue completion gets the
# same privacy/ownership reset as an explicit stop/restart.
stop_anchor = '''    fun stop(reason: String = "stopped") {\n'''
helper = '''    // AARISH_UI_ONLY_EPHEMERAL_CLEANUP_V4\n    // Keep no cross-mission target/provider ownership and no temporary screenshot evidence.\n    private fun clearMissionEphemeralState() {\n        persistentVisionMode = false\n        visionSessionId = ""\n        visionTurn = 0\n        lockedVisionProvider = null\n        lockedVisionProviderTaskId = null\n        lastTargetPackage = ""\n        lastObservedTargetFingerprint = ""\n        stagnantTargetTurns = 0\n        try {\n            File(service.cacheDir, "ai_sidecar").listFiles()?.forEach { it.delete() }\n        } catch (_: Throwable) {}\n    }\n\n'''
if 'AARISH_UI_ONLY_EPHEMERAL_CLEANUP_V4' not in s:
    if stop_anchor not in s:
        raise SystemExit('stop() anchor changed; refusing blind patch')
    s = s.replace(stop_anchor, helper + stop_anchor, 1)

old_stop_state = '''        persistentVisionMode = false\n        visionSessionId = ""\n        visionTurn = 0\n        lockedVisionProvider = null\n        lockedVisionProviderTaskId = null\n        // AARISH_UI_ONLY_TARGET_OWNERSHIP_V3\n        // A new mission must discover the foreground target from scratch. Keeping the\n        // previous mission package biases findBestTargetRoot() toward a stale app.\n        lastTargetPackage = ""\n        lastObservedTargetFingerprint = ""\n        // Screenshots are cache-only evidence; remove them as soon as a mission stops.\n        try {\n            File(service.cacheDir, "ai_sidecar").listFiles()?.forEach { it.delete() }\n        } catch (_: Throwable) {}\n'''
if old_stop_state not in s:
    raise SystemExit('v3 stop cleanup block changed; refusing blind patch')
s = s.replace(old_stop_state, '        clearMissionEphemeralState()\n', 1)

old_finish_rescue = '''    private fun finishRescue(ok: Boolean) {\n        missionRunning = false\n        waitingForAi = false\n        val cb = rescueCallback\n        rescueCallback = null\n        rescueMode = false\n        rescueExpectedAction = ""\n        releaseMissionWakeLock()\n        cb?.invoke(ok)\n    }\n'''
new_finish_rescue = '''    private fun finishRescue(ok: Boolean) {\n        missionRunning = false\n        waitingForAi = false\n        val cb = rescueCallback\n        rescueCallback = null\n        rescueMode = false\n        rescueExpectedAction = ""\n        clearMissionEphemeralState()\n        releaseMissionWakeLock()\n        cb?.invoke(ok)\n    }\n'''
if old_finish_rescue not in s:
    raise SystemExit('finishRescue() changed; refusing blind patch')
s = s.replace(old_finish_rescue, new_finish_rescue, 1)

old_finish_mission = '''    private fun finishMission(ok: Boolean, message: String) {\n        missionRunning = false\n        waitingForAi = false\n        rescueMode = false\n        rescueExpectedAction = ""\n        val cb = rescueCallback\n        rescueCallback = null\n        releaseMissionWakeLock()\n        toast(if (ok) "✅ $message" else "⚠️ $message")\n        cb?.invoke(ok)\n    }\n'''
new_finish_mission = '''    private fun finishMission(ok: Boolean, message: String) {\n        missionRunning = false\n        waitingForAi = false\n        rescueMode = false\n        rescueExpectedAction = ""\n        val cb = rescueCallback\n        rescueCallback = null\n        clearMissionEphemeralState()\n        releaseMissionWakeLock()\n        toast(if (ok) "✅ $message" else "⚠️ $message")\n        cb?.invoke(ok)\n    }\n'''
if old_finish_mission not in s:
    raise SystemExit('finishMission() changed; refusing blind patch')
s = s.replace(old_finish_mission, new_finish_mission, 1)

# Accessibility-only providers (Compose/WebView/custom AI apps) can visibly render our
# same-chat session marker without exposing transcript text. Use strict OCR of the exact
# random marker as a fallback; anything else still fails closed.
marker_tail = '''        return found\n    }\n\n    private fun askPhysicalAi(\n'''
marker_helper = '''        return found\n    }\n\n    // AARISH_UI_ONLY_SESSION_OCR_GUARD_V4\n    private fun verifyVisionSessionIdentity(\n        run: Int,\n        provider: Provider,\n        root: AccessibilityNodeInfo,\n        callback: (Boolean) -> Unit\n    ) {\n        if (!persistentVisionMode || visionTurn <= 0 || visionSessionId.isBlank()) {\n            callback(true)\n            return\n        }\n        if (visionSessionMarkerVisible(root)) {\n            callback(true)\n            return\n        }\n        val expectedMarker = visionSessionId\n        captureProviderOcr(provider) { ocr ->\n            if (!alive(run)) return@captureProviderOcr\n            val matched = expectedMarker.isNotBlank() &&\n                ocr.contains(expectedMarker, ignoreCase = true)\n            rememberHistory(\n                if (matched) "VISION SESSION GUARD: marker verified by OCR"\n                else "VISION SESSION GUARD: marker $expectedMarker absent in accessibility + OCR"\n            )\n            callback(matched)\n        }\n    }\n\n    private fun askPhysicalAi(\n'''
if marker_tail not in s:
    raise SystemExit('vision marker guard anchor changed; refusing blind patch')
s = s.replace(marker_tail, marker_helper, 1)

old_send = '''        fun sendFromReadyRoot(root: AccessibilityNodeInfo) {\n            if (persistentVisionMode && !visionSessionMarkerVisible(root)) {\n                // Fail closed: the provider app is open, but this is not provably the\n                // mission's existing conversation. Do not paste/send into an unknown chat.\n                rememberHistory("VISION SESSION GUARD: marker $visionSessionId missing on turn $visionTurn; send refused")\n                waitingForAi = false\n                callback(null)\n                return\n            }\n            ensurePromptAndSend(run, provider, root, prompt) { sent ->\n                if (!alive(run)) return@ensurePromptAndSend\n                if (!sent) {\n                    waitingForAi = false\n                    callback(null)\n                    return@ensurePromptAndSend\n                }\n                waitForCompleteResponse(run, provider, requestId, callback)\n            }\n        }\n'''
new_send = '''        fun sendFromReadyRoot(root: AccessibilityNodeInfo) {\n            verifyVisionSessionIdentity(run, provider, root) { verified ->\n                if (!alive(run)) return@verifyVisionSessionIdentity\n                if (!verified) {\n                    // Fail closed: provider is open, but this is not provably the mission's\n                    // existing conversation. Never paste/send into an unknown chat.\n                    waitingForAi = false\n                    callback(null)\n                    return@verifyVisionSessionIdentity\n                }\n                ensurePromptAndSend(run, provider, root, prompt) { sent ->\n                    if (!alive(run)) return@ensurePromptAndSend\n                    if (!sent) {\n                        waitingForAi = false\n                        callback(null)\n                        return@ensurePromptAndSend\n                    }\n                    waitForCompleteResponse(run, provider, requestId, callback)\n                }\n            }\n        }\n'''
if old_send not in s:
    raise SystemExit('sendFromReadyRoot() changed; refusing blind patch')
s = s.replace(old_send, new_send, 1)

sidecar.write_text(s, encoding='utf-8')

f = floating.read_text(encoding='utf-8')
old_checkbox = '        text = "📸 Teach Your AI — same chat + fresh screenshot after every action"\n'
new_checkbox = '        text = "📸 UI Relay / Teach Your AI — no API, MQTT or MCP; same chat + fresh screenshot after every action"\n'
if old_checkbox not in f:
    raise SystemExit('vision checkbox text changed; refusing blind patch')
f = f.replace(old_checkbox, new_checkbox, 1)
floating.write_text(f, encoding='utf-8')

# Surgical invariants.
final_s = sidecar.read_text(encoding='utf-8')
final_f = floating.read_text(encoding='utf-8')
assert final_s.count('AARISH_UI_ONLY_EPHEMERAL_CLEANUP_V4') == 1
assert final_s.count('clearMissionEphemeralState()') >= 3
assert 'AARISH_UI_ONLY_SESSION_OCR_GUARD_V4' in final_s
assert 'ocr.contains(expectedMarker, ignoreCase = true)' in final_s
assert 'no API, MQTT or MCP' in final_f
