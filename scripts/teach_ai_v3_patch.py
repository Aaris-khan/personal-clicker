from pathlib import Path
import re

p = Path('app/src/main/java/com/aarishkhan/aarishai/AiSidecarController.kt')
s = p.read_text(encoding='utf-8')

if 'AARISH_TEACH_AI_V3_JSON_RELAY' in s:
    raise SystemExit('v3 patch already applied')

# 1) Delegate command decoding to the independently unit-tested tolerant JSON/legacy parser.
parse_pattern = re.compile(
    r'    private fun parseCommand\(text: String, requestId: String\): AiCommand\? \{.*?\n    \}\n\n    private fun returnToTarget',
    re.S,
)
parse_replacement = '''    // AARISH_TEACH_AI_V3_JSON_RELAY
    // Provider may wrap the answer in prose/markdown. AiReplyParser extracts only the
    // correlated request-id command and rejects conflicting commands fail-closed.
    private fun parseCommand(text: String, requestId: String): AiCommand? =
        AiReplyParser.parse(text, requestId)?.let { parsed ->
            AiCommand(
                action = parsed.action,
                elementKey = parsed.element,
                payload = parsed.payload,
                expected = parsed.expected,
                visualToken = parsed.visual
            )
        }

    private fun returnToTarget'''
s, n = parse_pattern.subn(lambda _: parse_replacement, s, count=1)
if n != 1:
    raise SystemExit(f'parseCommand block changed; count={n}')

# 2) Android 8-10 should still get semantic Teach mode instead of being rejected only
# because AccessibilityService.takeScreenshot arrived in Android 11.
preflight_pattern = re.compile(
    r'\n\s*if \(persistentVision && Build\.VERSION\.SDK_INT < Build\.VERSION_CODES\.R\) \{\n'
    r'\s*return MissionPreflight\(false, reason = "Persistent Vision ke liye Android 11\+ chahiye"\)\n'
    r'\s*\}\n',
    re.S,
)
s, removed = preflight_pattern.subn('\n', s, count=1)
if removed not in (0, 1):
    raise SystemExit(f'unexpected preflight removal count={removed}')

old_capture = 'captureTargetScreen(run, forceVisual = persistentVisionMode) { state ->'
new_capture = 'captureTargetScreen(run, forceVisual = persistentVisionMode && Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) { state ->'
if old_capture not in s:
    raise SystemExit('persistent capture call changed')
s = s.replace(old_capture, new_capture, 1)

# 3) Teach prompt: JSON is preferred, legacy parser remains only for compatibility.
old_first_contract = '''                appendLine("OUTPUT CONTRACT:")
                appendLine("AARIS::<request-id>::<ACTION>::<ELEMENT>::<PAYLOAD>::<EXPECTED>::<VISUAL>::END")
                appendLine("Allowed ACTION: TAP, TAP_XY, LONG_TAP, SET_TEXT, SWIPE, SCROLL, BACK, HOME, WAIT, OPEN_APP, DONE, FAIL.")
                appendLine("TAP_XY PAYLOAD=x,y normalized 0..1.")
                appendLine("SWIPE PAYLOAD=x1,y1,x2,y2,durationMs normalized 0..1; duration 80..1500.")
                appendLine("SET_TEXT puts text in PAYLOAD and uses the supplied editable ELEMENT key.")
                appendLine("EXPECTED is required for actions that should visibly change state.")
                appendLine("VISUAL must echo the exact token visible inside the attached screenshot.")
                appendLine("No markdown, no explanation, exactly one machine line.")'''
new_first_contract = '''                appendLine("OUTPUT CONTRACT — PREFERRED JSON:")
                appendLine("Return exactly ONE flat JSON object with these keys:")
                appendLine("{\\\"request_id\\\":\\\"$requestId\\\",\\\"action\\\":\\\"TAP\\\",\\\"element\\\":\\\"E1\\\",\\\"payload\\\":\\\"\\\",\\\"expected\\\":\\\"visible proof\\\",\\\"visual\\\":\\\"NONE\\\"}")
                appendLine("Allowed action: TAP, TAP_XY, LONG_TAP, SET_TEXT, SWIPE, SCROLL, BACK, HOME, WAIT, OPEN_APP, DONE, FAIL.")
                appendLine("TAP_XY payload=x,y normalized 0..1. SWIPE payload=x1,y1,x2,y2,durationMs.")
                appendLine("SET_TEXT payload is the text and element is the editable E-key.")
                appendLine("EXPECTED is required for actions that should visibly change state.")
                appendLine("If a screenshot is attached, visual must echo its exact token; otherwise visual must be NONE.")
                appendLine("Do not add prose. If your UI adds prose anyway, the executor ignores it and reads only correlated JSON.")'''
if old_first_contract not in s:
    raise SystemExit('persistent first contract changed')
s = s.replace(old_first_contract, new_first_contract, 1)

old_continue_contract = '''                appendLine("Return exactly: AARIS::<request-id>::<ACTION>::<ELEMENT>::<PAYLOAD>::<EXPECTED>::<VISUAL>::END")
                appendLine("Allowed: TAP, TAP_XY, LONG_TAP, SET_TEXT, SWIPE, SCROLL, BACK, HOME, WAIT, OPEN_APP, DONE, FAIL.")
                appendLine("TAP_XY=x,y; SWIPE=x1,y1,x2,y2,durationMs; coordinates normalized 0..1.")
                appendLine("VISUAL must echo the exact token visible in this fresh screenshot.")'''
new_continue_contract = '''                appendLine("Return exactly ONE flat JSON object using request_id, action, element, payload, expected, visual.")
                appendLine("Allowed: TAP, TAP_XY, LONG_TAP, SET_TEXT, SWIPE, SCROLL, BACK, HOME, WAIT, OPEN_APP, DONE, FAIL.")
                appendLine("TAP_XY payload=x,y; SWIPE payload=x1,y1,x2,y2,durationMs; normalized 0..1.")
                appendLine("If the fresh screenshot has a token, echo it in visual; otherwise visual=NONE.")'''
if old_continue_contract not in s:
    raise SystemExit('persistent continuation contract changed')
s = s.replace(old_continue_contract, new_continue_contract, 1)

s = s.replace(
    'appendLine("CONTROL LOOP: You receive a fresh screenshot after EVERY single phone action.")',
    'appendLine("CONTROL LOOP: After EVERY single phone action you receive fresh state; a screenshot is attached when Android supports it.")',
    1,
)
s = s.replace(
    'appendLine("Continue the SAME goal and SAME conversation. Fresh screenshot attached.")',
    'appendLine("Continue the SAME goal and SAME conversation. Fresh state attached; pixel screenshot may be unavailable on older Android.")',
    1,
)
s = s.replace(
    'appendLine("FINAL RESPONSE must use request id $requestId and end with ::END")',
    'appendLine("FINAL JSON must use request_id=$requestId. Return only one correlated command object.")',
    1,
)

# Planner contract gets the same JSON protocol. This removes dependence on a special line
# while preserving legacy parsing for older already-running chats.
contract_pattern = re.compile(
    r'        val contract = buildString \{\n.*?\n        \}\n\n        val header = buildString \{',
    re.S,
)
new_contract = '''        val contract = buildString {
            appendLine("OUTPUT CONTRACT — MANDATORY AND HIGHEST PRIORITY:")
            appendLine("Return exactly ONE flat JSON object, no markdown and no prose:")
            appendLine("{\\\"request_id\\\":\\\"$requestId\\\",\\\"action\\\":\\\"TAP\\\",\\\"element\\\":\\\"E1\\\",\\\"payload\\\":\\\"\\\",\\\"expected\\\":\\\"visible proof\\\",\\\"visual\\\":\\\"NONE\\\"}")
            appendLine("request_id must exactly equal REQUEST IDENTIFIER from this request.")
            appendLine("Allowed action only: TAP, TAP_XY, LONG_TAP, SET_TEXT, SWIPE, SCROLL, BACK, HOME, WAIT, OPEN_APP, DONE, FAIL.")
            appendLine("visual = exact pixel token from attached image; NONE if no image; MISSING only when an expected image cannot be read.")
            appendLine("expected is mandatory for TAP, TAP_XY, LONG_TAP, SWIPE, SCROLL and DONE and must describe observable proof.")
            appendLine("SET_TEXT: payload=text. WAIT: payload=milliseconds. OPEN_APP: payload=human app name. FAIL: payload=reason.")
            appendLine("Never return two actions. Extra provider prose will be ignored, but conflicting correlated JSON commands are rejected.")
        }

        val header = buildString {'''
s, n = contract_pattern.subn(lambda _: new_contract, s, count=1)
if n != 1:
    raise SystemExit(f'planner contract block changed; count={n}')

old_tail = '''        val tail = buildString {
            appendLine("FINAL RESPONSE: use the exact REQUEST IDENTIFIER above in the <request-id> field.")
            appendLine("FINAL RESPONSE SUFFIX: ::END")
            append("PROMPT COMMIT: $requestId")
        }'''
new_tail = '''        val tail = buildString {
            appendLine("FINAL JSON: request_id must equal the exact REQUEST IDENTIFIER above.")
            appendLine("Return exactly one command object.")
            append("PROMPT COMMIT: $requestId")
        }'''
if old_tail not in s:
    raise SystemExit('planner tail changed')
s = s.replace(old_tail, new_tail, 1)

# 4) Bounded self-healing scroll inside the AI provider conversation. No coordinates, and
# never scroll while generation is active. This handles virtualized chat UIs where the newest
# assistant node is not currently exposed to Accessibility.
helper_anchor = '    private fun waitForCompleteResponse(run: Int, provider: Provider, requestId: String, callback: (AiCommand?) -> Unit) {'
if helper_anchor not in s:
    raise SystemExit('response wait anchor missing')
helper = '''    // AARISH_TEACH_AI_V3_PROVIDER_SCROLL
    private fun scrollProviderConversationTowardLatest(provider: Provider): Boolean {
        val root = findRootForPackage(providerPackage(provider)) ?: return false
        val screenW = service.resources.displayMetrics.widthPixels.coerceAtLeast(1)
        val screenH = service.resources.displayMetrics.heightPixels.coerceAtLeast(1)
        var best: AccessibilityNodeInfo? = null
        var bestScore = Int.MIN_VALUE
        walk(root, 4500) { node ->
            val usable = try { node.isScrollable && node.isVisibleToUser && node.isEnabled } catch (_: Throwable) { false }
            if (!usable) return@walk
            val b = Rect()
            try { node.getBoundsInScreen(b) } catch (_: Throwable) {}
            if (b.width() <= 0 || b.height() <= 0) return@walk
            val areaScore = (b.width().toLong() * b.height().toLong() / 1000L).coerceAtMost(Int.MAX_VALUE.toLong()).toInt()
            val widthBonus = if (b.width() >= screenW * 0.45f) 6000 else 0
            val centerBonus = if (b.centerY() in (screenH * 0.20f).toInt()..(screenH * 0.90f).toInt()) 1200 else 0
            val score = areaScore + widthBonus + centerBonus
            if (score > bestScore) { bestScore = score; best = node }
        }
        val node = best ?: return false
        return try { node.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD) } catch (_: Throwable) { false }
    }

'''
s = s.replace(helper_anchor, helper + helper_anchor, 1)

last_parsed = '        var lastParsed: AiCommand? = null\n'
if last_parsed not in s:
    raise SystemExit('lastParsed anchor missing')
s = s.replace(last_parsed, last_parsed + '        var providerLatestScrollAttempts = 0\n', 1)

early_ocr_marker = '''            // AARISH_AI_EARLY_OCR_FALLBACK_V7
'''
if early_ocr_marker not in s:
    raise SystemExit('early OCR marker missing')
scroll_logic = '''            // Some provider chat surfaces virtualize the newest response node. Once
            // generation is settled, nudge the largest provider scroll container toward
            // latest content at most twice, then fall through to OCR. Never coordinate-tap.
            val generationSettledForScroll = generationEndedAt > 0L && nowElapsed - generationEndedAt >= 700L
            val noGenerationSignalButMature = !sawGenerating && elapsed >= 6_000L
            if (parsed == null && !generating && providerLatestScrollAttempts < 2 &&
                (generationSettledForScroll || noGenerationSignalButMature)
            ) {
                providerLatestScrollAttempts++
                if (scrollProviderConversationTowardLatest(provider)) {
                    handler.postDelayed({ if (alive(run)) poll() }, 320L)
                    return
                }
            }

'''
s = s.replace(early_ocr_marker, scroll_logic + early_ocr_marker, 1)

# 5) Provider event tracking and all provider lookups in v2 already use providerPackage();
# assert that split/adjacent launch did not regress.
if 'FLAG_ACTIVITY_LAUNCH_ADJACENT' in s:
    raise SystemExit('split-screen launch flag unexpectedly present on current main')

p.write_text(s, encoding='utf-8')
