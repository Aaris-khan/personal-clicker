from pathlib import Path

ROOT = Path('app/src/main/java/com/aarishkhan/aarishai')
SIDE = ROOT / 'AiSidecarController.kt'
FCS = ROOT / 'FloatingControlService.kt'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one marker, found {count}')
    return text.replace(old, new, 1)


# V3.2 goal 1: a provider may render SEND visually but expose no useful Accessibility node.
# Preserve the user's demonstrated SEND tap as a normalized fallback point. COPY does NOT get
# this fallback because reply length moves its action row; COPY remains semantic/Accessibility/OCR.
f = FCS.read_text(encoding='utf-8')
if 'AARISH_AI_TEACH_SEND_XY_FALLBACK_V32' not in f:
    old = '''                val snapshot = AutoActionService.captureTargetSnapshot(x.toInt(), y.toInt(), screenW.toFloat(), screenH.toFloat())
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
'''
    new = '''                val accessibleSnapshot = AutoActionService.captureTargetSnapshot(
                    x.toInt(), y.toInt(), screenW.toFloat(), screenH.toFloat()
                )?.takeIf { it.targetPackage.orEmpty().equals(providerPackage, ignoreCase = true) }

                // AARISH_AI_TEACH_SEND_XY_FALLBACK_V32
                // Some custom AI apps draw an icon-only SEND control that never appears as a
                // useful Accessibility node. The user's demonstrated point is still valuable,
                // but only SEND may retain it: SEND lives beside the stable composer, whereas
                // COPY moves with reply length and would be unsafe as a blind coordinate.
                val learnedSnapshot = accessibleSnapshot ?: if (
                    role.equals(AiTeachProfileStore.ROLE_SEND, ignoreCase = true)
                ) {
                    TargetSnapshot(
                        targetClass = "TAUGHT_SEND_XY",
                        targetPackage = providerPackage,
                        targetRoleFlags = "click|xy_fallback",
                        targetTreePath = "TAUGHT_SEND_XY",
                        xPercent = (x / screenW.toFloat()).coerceIn(0f, 1f),
                        yPercent = (y / screenH.toFloat()).coerceIn(0f, 1f),
                        insideXPercent = 0.5f,
                        insideYPercent = 0.5f,
                        recordedScreenW = screenW,
                        recordedScreenH = screenH
                    )
                } else null
                cancelAiTeachTapV3()

                val gesture = RecordedGesture(
                    delayFromStart = 0L,
                    points = listOf(GesturePoint(x, y, 0L)),
                    targetText = learnedSnapshot?.targetText,
                    targetDesc = learnedSnapshot?.targetDesc,
                    targetId = learnedSnapshot?.targetId,
                    targetClass = learnedSnapshot?.targetClass,
                    targetPackage = learnedSnapshot?.targetPackage ?: providerPackage,
                    targetContextText = learnedSnapshot?.targetContextText,
                    targetChildText = learnedSnapshot?.targetChildText,
                    targetSiblingText = learnedSnapshot?.targetSiblingText,
                    targetRoleFlags = learnedSnapshot?.targetRoleFlags,
                    targetTreePath = learnedSnapshot?.targetTreePath,
                    targetLeft = learnedSnapshot?.targetLeft ?: -1,
                    targetTop = learnedSnapshot?.targetTop ?: -1,
                    targetRight = learnedSnapshot?.targetRight ?: -1,
                    targetBottom = learnedSnapshot?.targetBottom ?: -1,
                    xPercent = learnedSnapshot?.xPercent ?: (x / screenW.toFloat()),
                    yPercent = learnedSnapshot?.yPercent ?: (y / screenH.toFloat()),
                    targetWPercent = learnedSnapshot?.targetWPercent ?: 0f,
                    targetHPercent = learnedSnapshot?.targetHPercent ?: 0f,
                    insideXPercent = learnedSnapshot?.insideXPercent ?: 0.5f,
                    insideYPercent = learnedSnapshot?.insideYPercent ?: 0.5f,
                    recordedScreenW = screenW,
                    recordedScreenH = screenH
                )
                handler.postDelayed({
                    AutoActionService.playSingleLiveGestureSafe(gesture) {
                        callback(learnedSnapshot)
                    }
                }, 70L)
'''
    f = replace_once(f, old, new, 'teach SEND XY fallback')
    FCS.write_text(f, encoding='utf-8')


s = SIDE.read_text(encoding='utf-8')

# Point lookup is only consumed by SEND fallback. A finite normalized point is mandatory.
if 'AARISH_AI_LEARNED_POINT_V32' not in s:
    marker = '''    // AARISH_UNIVERSAL_AI_TEACH_RUNTIME_V3
    // User-taught provider controls are a structural fallback, never a blind coordinate replay.
    // Native accessibility submit remains first choice; generic semantic discovery remains last choice.
    private fun findLearnedProviderControl(
'''
    insert = '''    // AARISH_AI_LEARNED_POINT_V32
    private fun learnedProviderPoint(provider: Provider, role: String): Pair<Float, Float>? {
        val fp = AiTeachProfileStore.role(service, providerPackage(provider), role) ?: return null
        if (fp.xPercent.isNaN() || fp.yPercent.isNaN() ||
            fp.xPercent.isInfinite() || fp.yPercent.isInfinite()
        ) return null
        return fp.xPercent.coerceIn(0f, 1f) to fp.yPercent.coerceIn(0f, 1f)
    }

'''
    if marker not in s:
        raise SystemExit('learned control marker missing')
    s = s.replace(marker, insert + marker, 1)

# A taught point must let the readiness gate proceed even when no Accessibility SEND node exists.
old_ready = '''            val fallbackSubmitReady =
                latest != null && composer != null &&
                    (findLearnedProviderControl(provider, latest, AiTeachProfileStore.ROLE_SEND)
                        ?: findSendNode(latest, composer)) != null
'''
new_ready = '''            val fallbackSubmitReady =
                latest != null && composer != null && (
                    (findLearnedProviderControl(provider, latest, AiTeachProfileStore.ROLE_SEND)
                        ?: findSendNode(latest, composer)) != null ||
                        learnedProviderPoint(provider, AiTeachProfileStore.ROLE_SEND) != null
                    )
'''
if 'AARISH_AI_SEND_XY_RUNTIME_V32' not in s:
    s = replace_once(s, old_ready, new_ready, 'send readiness learned point')

    old_submit = '''            val send = latest?.let { rootNow ->
                findLearnedProviderControl(provider, rootNow, AiTeachProfileStore.ROLE_SEND)
                    ?: findSendNode(rootNow, freshComposer)
            }
            if (send == null) {
                finish(false)
                return
            }

            val baselineSerial = providerUiSerial.get()
            val accepted = clickNode(send)
            if (!accepted) {
                finish(false)
                return
            }
            awaitCommitEvidence(baselineSerial) { proved -> finish(proved) }
'''
    new_submit = '''            val send = latest?.let { rootNow ->
                findLearnedProviderControl(provider, rootNow, AiTeachProfileStore.ROLE_SEND)
                    ?: findSendNode(rootNow, freshComposer)
            }
            val taughtPoint = learnedProviderPoint(provider, AiTeachProfileStore.ROLE_SEND)
            if (send == null && taughtPoint == null) {
                finish(false)
                return
            }

            val baselineSerial = providerUiSerial.get()
            val accepted = if (send != null) {
                clickNode(send)
            } else {
                // AARISH_AI_SEND_XY_RUNTIME_V32
                // Coordinate fallback is allowed only after composerHasFullPrompt() above proved
                // this exact provider transaction is ready. Commit evidence must still prove SEND.
                val point = taughtPoint ?: return
                val providerBounds = findWindowBoundsForPackage(providerPackage(provider))
                rememberHistory("TEACH SEND: verified normalized fallback tap")
                tapNormalizedPoint(point.first, point.second, providerBounds)
            }
            if (!accepted) {
                finish(false)
                return
            }
            awaitCommitEvidence(baselineSerial) { proved -> finish(proved) }
'''
    s = replace_once(s, old_submit, new_submit, 'send runtime XY fallback')

# COPY controls repeat once per assistant message. Prefer the newest/bottom-most matching
# visible control; SEND keeps the original stable 2-D geometry score.
if 'AARISH_AI_COPY_LATEST_BIAS_V32' not in s:
    old_matcher = '''    private fun findLearnedProviderControl(
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
'''
    new_matcher = '''    private fun findLearnedProviderControl(
        provider: Provider,
        root: AccessibilityNodeInfo,
        role: String
    ): AccessibilityNodeInfo? {
        val fp = AiTeachProfileStore.role(service, providerPackage(provider), role) ?: return null
        val isCopyRole = role.equals(AiTeachProfileStore.ROLE_COPY, ignoreCase = true)
        val sw = service.resources.displayMetrics.widthPixels.toFloat().coerceAtLeast(2f)
        val sh = service.resources.displayMetrics.heightPixels.toFloat().coerceAtLeast(2f)
        var best: AccessibilityNodeInfo? = null
        var bestScore = Int.MIN_VALUE
        var bestCenterY = -1
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
            if (!fp.xPercent.isNaN() && b.width() > 0 && b.height() > 0) {
                val dx = kotlin.math.abs((b.centerX() / sw) - fp.xPercent)
                if (isCopyRole) {
                    // AARISH_AI_COPY_LATEST_BIAS_V32
                    // A copy action row moves vertically with reply length. Match its horizontal
                    // lane/shape, then strongly prefer the lowest visible matching row (latest reply).
                    when {
                        dx <= 0.04f -> score += 220
                        dx <= 0.10f -> score += 160
                        dx <= 0.20f -> score += 80
                        else -> score -= 180
                    }
                    score += ((b.centerY() / sh).coerceIn(0f, 1f) * 360f).toInt()
                } else if (!fp.yPercent.isNaN()) {
                    val dy = kotlin.math.abs((b.centerY() / sh) - fp.yPercent)
                    val distance = kotlin.math.sqrt(dx * dx + dy * dy)
                    when {
                        distance <= 0.035f -> score += 280
                        distance <= 0.08f -> score += 220
                        distance <= 0.16f -> score += 140
                        distance <= 0.28f -> score += 60
                        else -> score -= 320
                    }
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
            val centerY = if (b.height() > 0) b.centerY() else -1
            if (score > bestScore || (isCopyRole && score == bestScore && centerY > bestCenterY)) {
                bestScore = score
                bestCenterY = centerY
                best = n
            }
        }
        val threshold = if (isCopyRole) 320 else 280
        return best.takeIf { bestScore >= threshold }
    }
'''
    s = replace_once(s, old_matcher, new_matcher, 'role-aware taught matcher')

SIDE.write_text(s, encoding='utf-8')

# Static invariants keep future edits from silently removing the hardening.
side_text = SIDE.read_text(encoding='utf-8')
fcs_text = FCS.read_text(encoding='utf-8')
checks = {
    'send teach xy fallback': 'AARISH_AI_TEACH_SEND_XY_FALLBACK_V32' in fcs_text,
    'learned point helper': 'AARISH_AI_LEARNED_POINT_V32' in side_text,
    'verified send xy runtime': 'AARISH_AI_SEND_XY_RUNTIME_V32' in side_text,
    'latest copy bias': 'AARISH_AI_COPY_LATEST_BIAS_V32' in side_text,
    'no copy xy fallback': 'role.equals(AiTeachProfileStore.ROLE_SEND, ignoreCase = true)' in fcs_text,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit('v3.2 invariant failure: ' + ', '.join(failed))

print('AARISH_UNIVERSAL_AI_TEACH_RELAY_V32_HARDENED')
