from pathlib import Path

sidecar = Path('app/src/main/java/com/aarishkhan/aarishai/AiSidecarController.kt')
floating = Path('app/src/main/java/com/aarishkhan/aarishai/FloatingControlService.kt')

s = sidecar.read_text(encoding='utf-8')

old_stop = '''        persistentVisionMode = false
        visionSessionId = ""
        visionTurn = 0
        lockedVisionProvider = null
        lockedVisionProviderTaskId = null
        rescueMode = false
'''
new_stop = '''        persistentVisionMode = false
        visionSessionId = ""
        visionTurn = 0
        lockedVisionProvider = null
        lockedVisionProviderTaskId = null
        // AARISH_UI_ONLY_TARGET_OWNERSHIP_V3
        // A new mission must discover the foreground target from scratch. Keeping the
        // previous mission package biases findBestTargetRoot() toward a stale app.
        lastTargetPackage = ""
        lastObservedTargetFingerprint = ""
        // Screenshots are cache-only evidence; remove them as soon as a mission stops.
        try {
            File(service.cacheDir, "ai_sidecar").listFiles()?.forEach { it.delete() }
        } catch (_: Throwable) {}
        rescueMode = false
'''
if old_stop not in s:
    raise SystemExit('stop() state block changed; refusing blind patch')
s = s.replace(old_stop, new_stop, 1)

old_failure = '''    private fun markProviderFailure(provider: Provider, reason: String) {
        if (providerPreference != "AUTO") return
        val streak = (providerFailureStreak[provider] ?: 0) + 1
        providerFailureStreak[provider] = streak
        val cooldown = (15_000L * streak).coerceAtMost(90_000L)
        providerCooldownUntil[provider] = SystemClock.elapsedRealtime() + cooldown
        lastProviderAttempt = provider
        rememberHistory("PROVIDER ${provider.name} failed ($reason), failover armed")
    }
'''
new_failure = '''    private fun markProviderFailure(provider: Provider, reason: String) {
        if (providerPreference != "AUTO") return
        val streak = (providerFailureStreak[provider] ?: 0) + 1
        providerFailureStreak[provider] = streak
        val cooldown = (15_000L * streak).coerceAtMost(90_000L)
        providerCooldownUntil[provider] = SystemClock.elapsedRealtime() + cooldown
        lastProviderAttempt = provider
        rememberHistory("PROVIDER ${provider.name} failed ($reason), failover armed")

        // AARISH_UI_ONLY_PROVIDER_FAILOVER_V3
        // Persistent Vision normally pins one AI app to preserve the same conversation.
        // If AUTO sees repeated failures, keeping that lock defeats the cooldown/failover
        // machinery. Rotate to a fresh session so the next turn can choose another AI.
        if (persistentVisionMode && lockedVisionProvider == provider && streak >= 2) {
            lockedVisionProvider = null
            lockedVisionProviderTaskId = null
            visionSessionId = "PV" + UUID.randomUUID().toString().replace("-", "").take(10).uppercase(Locale.US)
            visionTurn = 0
            rememberHistory("VISION AUTO FAILOVER: released ${provider.name} after $streak failures; new session=$visionSessionId")
        }
    }
'''
if old_failure not in s:
    raise SystemExit('markProviderFailure() block changed; refusing blind patch')
s = s.replace(old_failure, new_failure, 1)

sidecar.write_text(s, encoding='utf-8')

f = floating.read_text(encoding='utf-8')
old_text = '            text = "No fixed button coordinates: AI composer/send/reply are rediscovered each turn. UI badle to engine re-detect karta hai."\n'
new_text = '            text = "UI Relay: API / MQTT / MCP ki zaroorat nahi. Accessibility + fresh screenshot se one-action-at-a-time control hota hai; fixed coordinates nahi, UI badle to engine re-detect karta hai."\n'
if old_text not in f:
    raise SystemExit('mission dialog help text changed; refusing blind patch')
f = f.replace(old_text, new_text, 1)
floating.write_text(f, encoding='utf-8')

# Static invariants for this surgical patch.
final_s = sidecar.read_text(encoding='utf-8')
final_f = floating.read_text(encoding='utf-8')
assert 'AARISH_UI_ONLY_TARGET_OWNERSHIP_V3' in final_s
assert 'AARISH_UI_ONLY_PROVIDER_FAILOVER_V3' in final_s
assert 'lastTargetPackage = ""' in final_s
assert 'lockedVisionProvider = null' in final_s
assert 'new session=$visionSessionId' in final_s
assert 'API / MQTT / MCP ki zaroorat nahi' in final_f
