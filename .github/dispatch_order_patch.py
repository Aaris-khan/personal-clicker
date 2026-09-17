from pathlib import Path

p = Path('app/src/main/java/com/aarishkhan/aarishai/AutoActionService.kt')
text = p.read_text(encoding='utf-8')

old = '''        val movement = hasRealMovement(points)
        val duration = kotlin.math.max(50L, points.maxOf { it.t.coerceAtLeast(0L) }).coerceAtMost(600000L)

        // AARISH_LOCAL_VISION_CACHE_DISPATCH_V1
        if (!movement && duration < 450L && aarishTryCachedVisionTap(recordedGesture, runId)) return

        if (!movement && duration <= 1200L && aarishTryFilesWordNodeClickV2(recordedGesture, runId, "Files click")) {
            // AARISH_UNIVERSAL_FILES_WORD_DISPATCH_V2
            return
        }

        // AARISH_HYBRID_SIMULTAN_V33_PLAYBACK_ORDER
        // Normal text tap ke liye priority: OCR -> Magnetic rescue -> XY last.
        // tryOcrTextTargetTap() ke andar OCR miss par aarishFallbackTapForOcrMiss()
        // chalega, jisme magnetic rescue add kiya gaya hai.
        if (!movement && aarishHasOcrIdentity(recordedGesture)) {
            if (tryOcrTextTargetTap(recordedGesture, runId)) return
        }

        val match = if (!movement || hasStrongSavedIdentity(recordedGesture) || hasSavedPercentAnchor(recordedGesture)) {
            findBestSmartTarget(recordedGesture)
        } else {
            null
        }

        // AARISH_OCR_TEXT_CLICK_V4_PLAYBACK_HOOK
        // Accessibility/magnetic fail hone par OCR se same recorded text dhoondo.
        if (!movement && match == null && aarishHasOcrIdentity(recordedGesture)) {
            if (tryOcrTextTargetTap(recordedGesture, runId)) return
        }

        // AARISH_LATE_TARGET_RETRY_HOOK_V1: target slow ho to raw fallback/strict skip se pehle smart retry.
        if (!movement && match == null &&
            (hasStrongSavedIdentity(recordedGesture) || hasSavedPercentAnchor(recordedGesture) || aarishHasAnyRichIdentity(recordedGesture))
        ) {
            if (trySmartTargetAfterShortSettle(recordedGesture, runId)) return
        }
'''

new = '''        val movement = hasRealMovement(points)
        val duration = kotlin.math.max(50L, points.maxOf { it.t.coerceAtLeast(0L) }).coerceAtMost(600000L)

        // AARISH_SEMANTIC_FIRST_DISPATCH_V4
        // Tap resolver priority:
        // 1) live Accessibility identity/structure
        // 2) OCR identity
        // 3) short live-target settle (vision can assist in parallel)
        // 4) explicit Files fallback
        // 5) short-lived vision cache
        // 6) raw/normalized XY last
        val match = if (!movement || hasStrongSavedIdentity(recordedGesture) || hasSavedPercentAnchor(recordedGesture)) {
            findBestSmartTarget(recordedGesture)
        } else {
            null
        }

        if (!movement && duration < 450L && match != null) {
            if (performSmartNodeClick(match, recordedGesture, runId)) return
        }

        if (!movement && aarishHasOcrIdentity(recordedGesture)) {
            if (tryOcrTextTargetTap(recordedGesture, runId)) return
        }

        if (!movement && match == null &&
            (hasStrongSavedIdentity(recordedGesture) || hasSavedPercentAnchor(recordedGesture) || aarishHasAnyRichIdentity(recordedGesture))
        ) {
            if (trySmartTargetAfterShortSettle(recordedGesture, runId)) return
        }

        if (!movement && duration < 450L && aarishTryFilesWordNodeClickV2(recordedGesture, runId, "Files click")) {
            return
        }

        if (!movement && duration < 450L && aarishTryCachedVisionTap(recordedGesture, runId)) return
'''

count = text.count(old)
if count != 1:
    raise SystemExit(f'Expected exactly one dispatch block, found {count}')
text = text.replace(old, new, 1)

duplicate = '''        if (!movement && duration < 450L && match != null) {
            if (performSmartNodeClick(match, recordedGesture, runId)) {
                return
            }
        }

'''

duplicate_count = text.count(duplicate)
if duplicate_count != 1:
    raise SystemExit(f'Expected one late duplicate smart-click block, found {duplicate_count}')
text = text.replace(duplicate, '', 1)

p.write_text(text, encoding='utf-8')

verify = p.read_text(encoding='utf-8')
marker = verify.find('AARISH_SEMANTIC_FIRST_DISPATCH_V4')
semantic = verify.find('performSmartNodeClick(match, recordedGesture, runId)', marker)
ocr = verify.find('tryOcrTextTargetTap(recordedGesture, runId)', marker)
settle = verify.find('trySmartTargetAfterShortSettle(recordedGesture, runId)', marker)
files = verify.find('aarishTryFilesWordNodeClickV2(recordedGesture, runId', marker)
cache = verify.find('aarishTryCachedVisionTap(recordedGesture, runId)', marker)
if min(marker, semantic, ocr, settle, files, cache) < 0 or not (semantic < ocr < settle < files < cache):
    raise SystemExit('Resolver priority verification failed')

print('Semantic-first dispatch order applied and verified.')
