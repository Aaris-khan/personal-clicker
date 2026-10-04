from pathlib import Path

ROOT = Path('app/src/main/java/com/aarishkhan/aarishai')
PROFILE = ROOT / 'AiTeachProfileStore.kt'
AUTO = ROOT / 'AutoActionService.kt'
SIDE = ROOT / 'AiSidecarController.kt'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one marker, found {count}')
    return text.replace(old, new, 1)

# SEND is sufficient for a usable relay. COPY is an optional high-fidelity fallback because
# Accessibility and OCR remain primary response readers.
p = PROFILE.read_text(encoding='utf-8')
if 'AARISH_AI_TEACH_SEND_SUFFICIENT_V31' not in p:
    p = replace_once(
        p,
        '        val ready: Boolean get() = send != null && copy != null\n',
        '''        // AARISH_AI_TEACH_SEND_SUFFICIENT_V31
        // SEND is the only mandatory taught control. COPY is optional because the runtime
        // reads Accessibility first and OCR last; this keeps providers without a Copy action usable.
        val ready: Boolean get() = send != null
        val copyReady: Boolean get() = copy != null
''',
        'profile readiness semantics'
    )
    PROFILE.write_text(p, encoding='utf-8')

# Persist SEND as soon as the user demonstrates it. Losing optional COPY training must never
# throw away the critical control that fixes the original submit failure.
a = AUTO.read_text(encoding='utf-8')
if 'AARISH_AI_TEACH_SAVE_SEND_EARLY_V31' not in a:
    old = '''                val armed = fcs.armAiTeachTapV3(AiTeachProfileStore.ROLE_SEND, pkg) { sendSnapshot ->
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
'''
    new = '''                val armed = fcs.armAiTeachTapV3(AiTeachProfileStore.ROLE_SEND, pkg) { sendSnapshot ->
                    if (sendSnapshot == null) {
                        Toast.makeText(this, "SEND learn nahi hua; dobara Teach chalao", Toast.LENGTH_LONG).show()
                        return@armAiTeachTapV3
                    }
                    // AARISH_AI_TEACH_SAVE_SEND_EARLY_V31
                    // SEND is the critical learned control. Save it immediately; COPY is optional.
                    val sendSaved = AiTeachProfileStore.saveVerifiedRole(
                        this,
                        pkg,
                        AiTeachProfileStore.ROLE_SEND,
                        sendSnapshot
                    )
                    if (!sendSaved || !AiTeachProfileStore.isReady(this, pkg)) {
                        Toast.makeText(this, "SEND profile save verify nahi hua", Toast.LENGTH_LONG).show()
                        return@armAiTeachTapV3
                    }
                    Toast.makeText(this, "✅ SEND learned • reply complete ho to COPY tap karke fallback bhi sikhao", Toast.LENGTH_LONG).show()

                    // Do not use a fixed AI wait. The teaching layer waits for the user's next tap,
                    // so slow/fast providers are both supported without recording a brittle delay.
                    handler.postDelayed({
                        fcs.armAiTeachTapV3(AiTeachProfileStore.ROLE_COPY, pkg) { copySnapshot ->
                            if (copySnapshot == null) {
                                Toast.makeText(this, "✅ SEND saved • COPY optional training skipped", Toast.LENGTH_LONG).show()
                                return@armAiTeachTapV3
                            }
                            val copySaved = AiTeachProfileStore.saveVerifiedRole(
                                this,
                                pkg,
                                AiTeachProfileStore.ROLE_COPY,
                                copySnapshot
                            )
                            Toast.makeText(
                                this,
                                if (copySaved) "✅ AI relay trained: SEND + COPY learned" else "✅ SEND saved • COPY save verify nahi hua",
                                Toast.LENGTH_LONG
                            ).show()
                        }
                    }, 450L)
                }
'''
    a = replace_once(a, old, new, 'save SEND immediately')
    AUTO.write_text(a, encoding='utf-8')

# Original bug killer: in Persistent Vision, a failed physical-AI transaction must not schedule
# another whole mission turn, because a whole turn captures and stages the screenshot again.
# Fail closed after the already-bounded send/response transaction instead.
s = SIDE.read_text(encoding='utf-8')
if 'AARISH_AI_NO_DUPLICATE_REATTACH_V31' not in s:
    old = '''                if (command == null) {
                    markProviderFailure(provider, "open/send/response failure")
                    returnToTarget(run, lastTargetPackage) {
                        if (alive(run)) failTurn(run, "AI response parse/timeout")
                    }
                    return@askPhysicalAi
                }
'''
    new = '''                if (command == null) {
                    markProviderFailure(provider, "open/send/response failure")
                    returnToTarget(run, lastTargetPackage) {
                        if (!alive(run)) return@returnToTarget
                        if (persistentVisionMode) {
                            // AARISH_AI_NO_DUPLICATE_REATTACH_V31
                            // A Persistent Vision turn has already staged its screenshot. Re-entering
                            // nextMissionTurn here would attach the same visual evidence again and can
                            // create the exact photo/photo/photo loop seen in real-device testing.
                            // The send/read transaction already has readiness, commit, Accessibility,
                            // learned-COPY and OCR waits, so an unverified result is terminal and safe.
                            finishMission(
                                false,
                                "AI relay submit/reply verify nahi hua. Screenshot dobara attach nahi kiya. TEACH AI se SEND/COPY re-train karo."
                            )
                        } else {
                            failTurn(run, "AI response parse/timeout")
                        }
                    }
                    return@askPhysicalAi
                }
'''
    s = replace_once(s, old, new, 'persistent vision duplicate reattach guard')
    SIDE.write_text(s, encoding='utf-8')

# Static invariants: fail early if later edits accidentally undo the safety contract.
profile_text = PROFILE.read_text(encoding='utf-8')
auto_text = AUTO.read_text(encoding='utf-8')
side_text = SIDE.read_text(encoding='utf-8')
checks = {
    'send sufficient': 'val ready: Boolean get() = send != null' in profile_text,
    'send saved early': 'AARISH_AI_TEACH_SAVE_SEND_EARLY_V31' in auto_text,
    'no duplicate guard': 'AARISH_AI_NO_DUPLICATE_REATTACH_V31' in side_text,
    'persistent terminal failure': 'Screenshot dobara attach nahi kiya' in side_text,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit('v3.1 invariant failure: ' + ', '.join(failed))

print('AARISH_UNIVERSAL_AI_TEACH_RELAY_V31_HARDENED')
