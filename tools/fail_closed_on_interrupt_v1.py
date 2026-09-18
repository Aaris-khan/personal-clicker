from pathlib import Path
p=Path(__file__).resolve().parents[1]/"app/src/main/java/com/aarishkhan/aarishai/AutoActionService.kt"
text=p.read_text(encoding="utf-8")
old='''    override fun onInterrupt() {
        stopPlaybackInternal(showToast = false)
    }
'''
new='''    override fun onInterrupt() {
        // AARISH_AI_INTERRUPT_FAIL_CLOSED_V1
        // Accessibility interruption means executor/verifier guarantees are temporarily
        // unavailable. Stop both replay and Autonomous AI rather than letting queued
        // sidecar callbacks keep acting without a trustworthy live accessibility channel.
        stopPlaybackInternal(showToast = false)
        try { aiSidecarController.stop("accessibility interrupted") } catch (_: Throwable) {}
    }
'''
if text.count(old)!=1:
    raise SystemExit(f"onInterrupt anchor count={text.count(old)}")
p.write_text(text.replace(old,new,1),encoding="utf-8")
print("Accessibility interruption now fails closed for replay + autonomous sidecar.")
