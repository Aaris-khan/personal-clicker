from pathlib import Path
import re

AUTO = Path("app/src/main/java/com/aarishkhan/aarishai/AutoActionService.kt")
FLOAT = Path("app/src/main/java/com/aarishkhan/aarishai/FloatingControlService.kt")

auto = AUTO.read_text(encoding="utf-8")
floating = FLOAT.read_text(encoding="utf-8")

if "AARISH_PRECISION_TARGET_ENGINE_V3" in auto and "AARISH_PRECISION_RECORDING_V3" in floating:
    print("Precision upgrade already present; nothing to do.")
    raise SystemExit(0)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 exact match, found {count}")
    return text.replace(old, new, 1)


def sub_once(text: str, pattern: str, replacement, label: str) -> str:
    matches = list(re.finditer(pattern, text, flags=re.S))
    if len(matches) != 1:
        raise SystemExit(f"{label}: expected 1 regex match, found {len(matches)}")
    m = matches[0]
    repl = replacement(m) if callable(replacement) else replacement
    return text[:m.start()] + repl + text[m.end():]


# 1. Recording target root: choose the topmost/focused window, not the largest window.
root_replacement = '''    // AARISH_PRECISION_TARGET_ENGINE_V3
    private fun getRealAppRootForPoint(tapX: Int?, tapY: Int?): AccessibilityNodeInfo? {
        val myPackage = packageName
        var bestRoot: AccessibilityNodeInfo? = null
        var bestFocusRank = Int.MIN_VALUE
        var bestLayer = Int.MIN_VALUE
        var bestArea = Long.MAX_VALUE

        fun isBadPackage(pkg: String): Boolean {
            val p = pkg.lowercase(java.util.Locale.US)
            return p.isBlank() ||
                p == myPackage.lowercase(java.util.Locale.US) ||
                p.contains("inputmethod") ||
                p.contains("keyboard")
        }

        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.LOLLIPOP) {
            try {
                for (window in windows) {
                    val root = try { window.root } catch (_: Throwable) { null } ?: continue
                    val pkg = try { root.packageName?.toString().orEmpty() } catch (_: Throwable) { "" }
                    if (isBadPackage(pkg)) continue

                    val bounds = Rect()
                    if (!safeBounds(root, bounds) || bounds.width() <= 0 || bounds.height() <= 0) continue
                    if (tapX != null && tapY != null && !bounds.contains(tapX, tapY)) continue

                    val focused = try { window.isFocused } catch (_: Throwable) { false }
                    val active = try { window.isActive } catch (_: Throwable) { false }
                    val focusRank = (if (focused) 2 else 0) + (if (active) 1 else 0)
                    val layer = try { window.layer } catch (_: Throwable) { 0 }
                    val area = bounds.width().toLong().coerceAtLeast(1L) * bounds.height().toLong().coerceAtLeast(1L)

                    val better =
                        bestRoot == null ||
                            focusRank > bestFocusRank ||
                            (focusRank == bestFocusRank && layer > bestLayer) ||
                            (focusRank == bestFocusRank && layer == bestLayer && area < bestArea)

                    if (better) {
                        bestRoot = root
                        bestFocusRank = focusRank
                        bestLayer = layer
                        bestArea = area
                    }
                }
            } catch (_: Throwable) {
            }
        }

        if (bestRoot != null) return bestRoot

        val fallbackRoot = rootInActiveWindow ?: return null
        val fallbackPkg = try { fallbackRoot.packageName?.toString().orEmpty() } catch (_: Throwable) { "" }
        return if (isBadPackage(fallbackPkg)) null else fallbackRoot
    }

    // ==========================================================
    // 🔥 RECORDING TIME SNAPSHOT'''
auto = sub_once(
    auto,
    r'''    private fun getRealAppRootForPoint\(tapX: Int\?, tapY: Int\?\): AccessibilityNodeInfo\? \{.*?\n    \}\n\n    // ==========================================================\n    // 🔥 RECORDING TIME SNAPSHOT''',
    root_replacement,
    "topmost window resolver",
)

# 2. Ignore invisible/dead descendants during coordinate hit-testing.
auto = replace_once(
    auto,
    '''                val bounds = Rect()
                if (!safeBounds(node, bounds) || !bounds.contains(x, y)) continue
''',
    '''                if (!safeVisible(node) || !safeEnabled(node)) continue
                val bounds = Rect()
                if (!safeBounds(node, bounds) || !bounds.contains(x, y)) continue
''',
    "visible coordinate hit-test",
)

# 3. Nearby "Files" text must not hijack a different tapped control.
files_primary_replacement = '''    // AARISH_PRECISION_FILES_IDENTITY_V3
    val directFilesWordPrimaryV3 =
        aarishNodeFilesLabelV2(touchedNode) ?: aarishNodeFilesLabelV2(clickNode)
    val aarishFilesWordPrimaryV2 = directFilesWordPrimaryV3 ?: if (
        primaryText.isNullOrBlank() && primaryDesc.isNullOrBlank()
    ) {
        aarishFindFilesWordNearTapV2(
            root = root,
            touchedNode = touchedNode,
            clickNode = clickNode,
            tapX = x,
            tapY = y,
            screenW = safeW,
            screenH = safeH
        )
    } else {
        null
    }
    val aarishPrimaryTextV2 = aarishFilesWordPrimaryV2 ?: primaryText
    val aarishPrimaryDescV2 = aarishFilesWordPrimaryV2 ?: primaryDesc
'''
auto = sub_once(
    auto,
    r'''    val aarishFilesWordPrimaryV2 = aarishFindFilesWordNearTapV2\(.*?    val aarishPrimaryDescV2 = aarishFilesWordPrimaryV2 \?: primaryDesc\n''',
    files_primary_replacement,
    "files primary identity",
)

# 4. Exact text/description hits must stay in the recorded package.
auto = replace_once(
    auto,
    "        val textOk = !savedText.isNullOrBlank() &&\n",
    "        val textOk = packageOk && !savedText.isNullOrBlank() &&\n",
    "exact text package scope",
)
auto = replace_once(
    auto,
    "        val descOk = !savedDesc.isNullOrBlank() &&\n",
    "        val descOk = packageOk && !savedDesc.isNullOrBlank() &&\n",
    "exact desc package scope",
)

# 5. Fuzzy candidates in a different package get a strong penalty, but are not
# totally forbidden so old recordings can still recover if their saved package was noisy.
auto = replace_once(
    auto,
    '''            val actionNode = findClickableParent(node) ?: node

            val nodeText = safeText(node)?.trim()
''',
    '''            val actionNode = findClickableParent(node) ?: node

            val savedPackageForScore = aarishSavedPackageFromId(gesture)
            val packageMismatchForScore = savedPackageForScore.isNotBlank() &&
                aarishNodePackage(node) != savedPackageForScore &&
                aarishNodePackage(actionNode) != savedPackageForScore

            val nodeText = safeText(node)?.trim()
''',
    "smart score package state",
)

def add_package_penalty(m):
    return m.group(1) + "            if (packageMismatchForScore) score -= 180\n" + m.group(2)

auto = sub_once(
    auto,
    r'''(    private fun scoreNode\(.*?            var score = 0\n)(            var primaryHits = 0\n)''',
    add_package_penalty,
    "smart score package penalty",
)

# 6. Cached visual coordinates expire quickly; dynamic chat UIs move too fast for 30s cache.
auto = replace_once(
    auto,
    "if (age < 0L || age > 30_000L) {",
    "if (age < 0L || age > 1_800L) {",
    "vision cache ttl",
)
auto = replace_once(
    auto,
    "if (cached.confidence < 0.50f || !aarishVisionPackageLooksSafe(g)) {",
    "if (cached.confidence < 0.72f || !aarishVisionPackageLooksSafe(g)) {",
    "vision cache confidence",
)

# 7. File rescue is restricted to real active/focused file-manager windows.
file_pkg_replacement = '''    private fun aarishFileManagerPackageV1(pkg: String?): Boolean {
        // AARISH_FILE_MANAGER_RESCUE_V3_STRICT
        val p = pkg.orEmpty().trim().lowercase(java.util.Locale.US)
        if (p.isBlank()) return false

        return p == "com.android.documentsui" ||
            p == "com.google.android.documentsui" ||
            p.contains(".documentsui") ||
            p.contains("filemanager") ||
            p.contains("fileexplorer") ||
            p.contains("globalfileexplorer") ||
            p.contains(".myfiles") ||
            p.endsWith(".files") ||
            p == "com.google.android.apps.nbu.files"
    }

    private fun aarishFileNodeActionCandidateV1'''
auto = sub_once(
    auto,
    r'''    private fun aarishFileManagerPackageV1\(pkg: String\?\): Boolean \{.*?\n    \}\n\n    private fun aarishFileNodeActionCandidateV1''',
    file_pkg_replacement,
    "strict file-manager packages",
)

file_rescue_replacement = '''    private fun aarishTryFileManagerNodeRescueV1(
        x: Float,
        y: Float,
        runId: Int?,
        label: String = "File picker clicked"
    ): Boolean {
        // AARISH_FILE_MANAGER_RESCUE_V3_STRICT
        if (runId != null && !isSamePlaybackRun(runId)) return false

        val targetX = x.toInt()
        val targetY = y.toInt()
        val roots = mutableListOf<AccessibilityNodeInfo>()

        fun addFileRoot(root: AccessibilityNodeInfo?) {
            if (root == null) return
            val pkg = try { root.packageName?.toString() } catch (_: Throwable) { null }
            if (!aarishFileManagerPackageV1(pkg)) return
            val b = Rect()
            if (safeBounds(root, b) && b.width() > 0 && b.height() > 0 && !b.contains(targetX, targetY)) return
            if (roots.none { it === root }) roots.add(root)
        }

        try { addFileRoot(rootInActiveWindow) } catch (_: Throwable) {}

        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.LOLLIPOP) {
            try {
                for (w in windows) {
                    val activeOrFocused = try { w.isActive || w.isFocused } catch (_: Throwable) { false }
                    if (!activeOrFocused) continue
                    addFileRoot(try { w.root } catch (_: Throwable) { null })
                }
            } catch (_: Throwable) {}
        }

        if (roots.isEmpty()) return false

        var bestNode: AccessibilityNodeInfo? = null
        var bestArea = Int.MAX_VALUE
        var bestDepth = -1
        var scanned = 0

        fun remember(candidate: AccessibilityNodeInfo?, depth: Int) {
            if (candidate == null || !safeVisible(candidate) || !safeEnabled(candidate) || !safeClickable(candidate)) return
            val b = Rect()
            if (!safeBounds(candidate, b) || b.width() <= 0 || b.height() <= 0 || !b.contains(targetX, targetY)) return
            val area = b.width().coerceAtLeast(1) * b.height().coerceAtLeast(1)
            val better = bestNode == null || area < bestArea || (area == bestArea && depth > bestDepth)
            if (better) {
                bestNode = candidate
                bestArea = area
                bestDepth = depth
            }
        }

        try {
            for (root in roots) {
                val stack = java.util.ArrayDeque<Pair<AccessibilityNodeInfo, Int>>()
                stack.add(Pair(root, 0))
                while (!stack.isEmpty() && scanned < 2600) {
                    val item = stack.removeLast()
                    val node = item.first
                    val depth = item.second
                    scanned++

                    val bounds = Rect()
                    if (!safeBounds(node, bounds) || bounds.width() <= 0 || bounds.height() <= 0 || !bounds.contains(targetX, targetY)) continue
                    remember(aarishFileNodeActionCandidateV1(node), depth)

                    val count = safeChildCount(node)
                    for (i in count - 1 downTo 0) {
                        val child = safeChild(node, i)
                        if (child != null) stack.add(Pair(child, depth + 1))
                    }
                }
            }
        } catch (_: Throwable) {}

        val node = bestNode ?: return false
        val clicked = try {
            node.performAction(AccessibilityNodeInfo.ACTION_CLICK) ||
                node.performAction(AccessibilityNodeInfo.ACTION_SELECT)
        } catch (_: Throwable) {
            false
        }
        if (!clicked) return false

        try {
            android.util.Log.d(
                "AarishAI_FileRescue",
                "Strict file-node click x=$targetX y=$targetY area=$bestArea depth=$bestDepth scanned=$scanned"
            )
        } catch (_: Throwable) {}
        showTinyToast(label)
        return true
    }

    private fun aarishShowVisualClickIndicator'''
auto = sub_once(
    auto,
    r'''    private fun aarishTryFileManagerNodeRescueV1\(.*?\n    \}\n\n    private fun aarishShowVisualClickIndicator''',
    file_rescue_replacement,
    "strict file-manager rescue",
)

# 8. Recording uses both ACTION_DOWN and a fresh pre-replay snapshot, choosing richer identity.
helper = '''    // AARISH_PRECISION_RECORDING_V3
    private fun chooseBestRecordingSnapshotV3(
        downSnapshot: TargetSnapshot?,
        freshSnapshot: TargetSnapshot?
    ): TargetSnapshot? {
        fun score(s: TargetSnapshot?): Int {
            if (s == null) return Int.MIN_VALUE
            var value = 0
            if (!s.targetId.isNullOrBlank() && !s.targetId!!.startsWith("ocr:")) value += 140
            if (!s.targetDesc.isNullOrBlank() && s.targetDesc != "OCR_TEXT_TARGET") value += 115
            if (!s.targetText.isNullOrBlank() && !s.targetText!!.startsWith("OCR:")) value += 105
            if (!s.targetPackage.isNullOrBlank()) value += 80
            if (!s.targetTreePath.isNullOrBlank() && s.targetTreePath != "OCR") value += 75
            if (!s.targetRoleFlags.isNullOrBlank() && s.targetRoleFlags != "OCR_VISIBLE_TEXT") value += 45
            if (!s.targetContextText.isNullOrBlank()) value += 28
            if (!s.targetSiblingText.isNullOrBlank()) value += 18
            if (s.targetRight > s.targetLeft && s.targetBottom > s.targetTop) value += 35
            if (s.targetWPercent > 0f && s.targetHPercent > 0f) value += 20
            return value
        }

        val downScore = score(downSnapshot)
        val freshScore = score(freshSnapshot)
        return if (freshScore >= downScore) freshSnapshot ?: downSnapshot else downSnapshot ?: freshSnapshot
    }

    private fun snapshotHasUsefulIdentity(snapshot: TargetSnapshot?): Boolean {
'''
floating = replace_once(
    floating,
    "    private fun snapshotHasUsefulIdentity(snapshot: TargetSnapshot?): Boolean {\n",
    helper,
    "recording snapshot selector helper",
)

floating = replace_once(
    floating,
    '''        val snapshot = if (forceXyOnly) {
            null
        } else {
            currentSnapshot ?: captureSnapshotFor(
                firstP.x.toInt(),
                firstP.y.toInt()
            )
        }
''',
    '''        val snapshot = if (forceXyOnly) {
            null
        } else {
            chooseBestRecordingSnapshotV3(
                currentSnapshot,
                captureSnapshotFor(firstP.x.toInt(), firstP.y.toInt())
            )
        }
''',
    "dual recording snapshot",
)

# 9. OCR supplements semantic identity; it must not overwrite a real Send/Copy/Mic/etc label.
floating = replace_once(
    floating,
    '''        fun realId(v: String?): Boolean = !v.isNullOrBlank() && !v.startsWith("ocr:")
        fun realDesc(v: String?): Boolean = !v.isNullOrBlank() && v != "OCR_TEXT_TARGET"
        fun realClass(v: String?): Boolean = !v.isNullOrBlank() && v != "OCR_TEXT"
        fun realTree(v: String?): Boolean = !v.isNullOrBlank() && v != "OCR"
        fun realRole(v: String?): Boolean = !v.isNullOrBlank() && v != "OCR_VISIBLE_TEXT"
        fun realSibling(v: String?): Boolean = !v.isNullOrBlank() && !v.startsWith("ocr_bounds=")
        fun clean(v: String?): String? = v?.takeIf { it.isNotBlank() }
''',
    '''        fun realId(v: String?): Boolean = !v.isNullOrBlank() && !v.startsWith("ocr:")
        fun realDesc(v: String?): Boolean = !v.isNullOrBlank() && v != "OCR_TEXT_TARGET"
        fun realClass(v: String?): Boolean = !v.isNullOrBlank() && v != "OCR_TEXT"
        fun realTree(v: String?): Boolean = !v.isNullOrBlank() && v != "OCR"
        fun realRole(v: String?): Boolean = !v.isNullOrBlank() && v != "OCR_VISIBLE_TEXT"
        fun realSibling(v: String?): Boolean = !v.isNullOrBlank() && !v.startsWith("ocr_bounds=")
        fun realText(v: String?): Boolean {
            if (v.isNullOrBlank() || v.startsWith("OCR:")) return false
            val n = v.trim().lowercase(java.util.Locale.US)
                .replace(Regex("[^a-z0-9\\u0600-\\u06FF\\u0750-\\u077F\\u0900-\\u097F]+"), " ")
                .replace(Regex("\\s+"), " ")
                .trim()
            if (n.length < 2) return false
            return n !in setOf("view", "text", "button", "image", "layout", "android", "widget", "item")
        }
        fun clean(v: String?): String? = v?.takeIf { it.isNotBlank() }
''',
    "ocr semantic helper",
)

floating = replace_once(
    floating,
    "            targetText = clean(snapshot.targetText) ?: gesture.targetText,\n",
    '''            targetText = if (realId(gesture.targetId) || realDesc(gesture.targetDesc) || realText(gesture.targetText)) {
                clean(gesture.targetText) ?: clean(snapshot.targetText)
            } else {
                clean(snapshot.targetText) ?: gesture.targetText
            },
''',
    "ocr semantic priority",
)

AUTO.write_text(auto, encoding="utf-8")
FLOAT.write_text(floating, encoding="utf-8")

checks = {
    "precision target marker": auto.count("AARISH_PRECISION_TARGET_ENGINE_V3") == 1,
    "strict file rescue marker": auto.count("AARISH_FILE_MANAGER_RESCUE_V3_STRICT") >= 2,
    "vision ttl": "age > 1_800L" in auto,
    "package exact text": "val textOk = packageOk &&" in auto,
    "package exact desc": "val descOk = packageOk &&" in auto,
    "recording marker": floating.count("AARISH_PRECISION_RECORDING_V3") == 1,
    "dual snapshot": "chooseBestRecordingSnapshotV3(" in floating,
    "semantic OCR": "realText(gesture.targetText)" in floating,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit("Verification failed: " + ", ".join(failed))

print("Precision patch applied and structural checks passed.")
