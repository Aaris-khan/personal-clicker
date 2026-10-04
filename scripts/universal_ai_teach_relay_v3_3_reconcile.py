from pathlib import Path

FCS = Path('app/src/main/java/com/aarishkhan/aarishai/FloatingControlService.kt')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one marker, found {count}')
    return text.replace(old, new, 1)


# Runs AFTER v3_2_scroll_teach. The scroll patch intentionally rewrites the whole teaching
# touch handler, so restore the SEND-only XY fallback inside that final handler without
# sacrificing swipe-through teaching. COPY never gets blind XY fallback.
s = FCS.read_text(encoding='utf-8')
if 'AARISH_AI_TEACH_SEND_XY_SCROLL_RECONCILE_V33' not in s:
    old = '''                        val snapshot = AutoActionService.captureTargetSnapshot(
                            x.toInt(),
                            y.toInt(),
                            screenW.toFloat(),
                            screenH.toFloat()
                        )?.takeIf {
                            it.targetPackage.orEmpty().equals(providerPackage, ignoreCase = true)
                        }
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
    new = '''                        val accessibleSnapshot = AutoActionService.captureTargetSnapshot(
                            x.toInt(),
                            y.toInt(),
                            screenW.toFloat(),
                            screenH.toFloat()
                        )?.takeIf {
                            it.targetPackage.orEmpty().equals(providerPackage, ignoreCase = true)
                        }

                        // AARISH_AI_TEACH_SEND_XY_SCROLL_RECONCILE_V33
                        // If an icon-only SEND is invisible to Accessibility, retain the user's
                        // demonstrated normalized point. This fallback is SEND-only because the
                        // composer/send row is stable; a reply COPY row moves with response length.
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
    s = replace_once(s, old, new, 'scroll-teach SEND XY reconciliation')
    FCS.write_text(s, encoding='utf-8')

text = FCS.read_text(encoding='utf-8')
checks = {
    'scroll-through teaching retained': 'AARISH_AI_TEACH_SCROLL_THROUGH_V32' in text,
    'send xy reconciled': 'AARISH_AI_TEACH_SEND_XY_SCROLL_RECONCILE_V33' in text,
    'send-only fallback': 'role.equals(AiTeachProfileStore.ROLE_SEND, ignoreCase = true)' in text,
    'copy scroll instruction retained': 'zarurat ho to pehle scroll karo' in text,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit('v3.3 invariant failure: ' + ', '.join(failed))

print('AARISH_UNIVERSAL_AI_TEACH_RELAY_V33_RECONCILED')
