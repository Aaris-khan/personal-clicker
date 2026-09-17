from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {count}")
    return text.replace(old, new, 1)


auto_path = Path('app/src/main/java/com/aarishkhan/aarishai/AutoActionService.kt')
auto = auto_path.read_text(encoding='utf-8')

if 'AARISH_AI_SIDECAR_BRIDGE_V1' not in auto:
    bridge_anchor = '''        // 🔥 Recording ke time button ki kundali nikalne ke liye\n'''
    bridge = '''        // AARISH_AI_SIDECAR_BRIDGE_V1\n        fun startAutonomousMission(context: Context, goal: String, provider: String = "AUTO"): Boolean {\n            val service = instance\n            if (service == null) {\n                Toast.makeText(context, "Accessibility Service ready nahi hai", Toast.LENGTH_SHORT).show()\n                return false\n            }\n            if (service.isPlayingInternal) service.stopPlaybackInternal()\n            return service.aiSidecarController.startMission(goal, provider)\n        }\n\n        fun stopAiAgent(context: Context): Boolean {\n            val service = instance ?: return false\n            service.aiSidecarController.stop("stopped")\n            return true\n        }\n\n        fun isAiAgentRunning(): Boolean = instance?.aiSidecarController?.isRunning() == true\n\n'''
    auto = replace_once(auto, bridge_anchor, bridge + bridge_anchor, 'auto bridge')

if 'AARISH_AI_SIDECAR_CONTROLLER_FIELD_V1' not in auto:
    field_anchor = '''    private val handler = Handler(Looper.getMainLooper())\n'''
    field = '''    // AARISH_AI_SIDECAR_CONTROLLER_FIELD_V1\n    private val aiSidecarController: AiSidecarController by lazy { AiSidecarController(this) }\n\n'''
    auto = replace_once(auto, field_anchor, field_anchor + field, 'auto field')

if 'AARISH_AI_SIDECAR_DESTROY_V1' not in auto:
    destroy_anchor = '''        if (instance == this) {\n            instance = null\n        }\n'''
    destroy = '''        // AARISH_AI_SIDECAR_DESTROY_V1\n        try { aiSidecarController.stop("service stopped") } catch (_: Throwable) {}\n\n'''
    auto = replace_once(auto, destroy_anchor, destroy + destroy_anchor, 'auto destroy')

if 'AARISH_AI_RESCUE_ON_REPLAY_MISS_V1' not in auto:
    miss_old = '''                if (elapsed >= maxWait) {\n                    showTinyToast("Target 10s me nahi mila")\n                    finishOnce()\n                    return\n                }\n'''
    miss_new = '''                if (elapsed >= maxWait) {\n                    // AARISH_AI_RESCUE_ON_REPLAY_MISS_V1\n                    val rescueStarted = try {\n                        aiSidecarController.rescueRecordedFailure(recordedGesture) { ok ->\n                            if (ok) showTinyToast("AI rescue complete")\n                            else showTinyToast("AI rescue failed")\n                            finishOnce()\n                        }\n                    } catch (_: Throwable) {\n                        false\n                    }\n                    if (!rescueStarted) {\n                        showTinyToast("Target 10s me nahi mila")\n                        finishOnce()\n                    }\n                    return\n                }\n'''
    auto = replace_once(auto, miss_old, miss_new, 'replay rescue')

auto_path.write_text(auto, encoding='utf-8')

float_path = Path('app/src/main/java/com/aarishkhan/aarishai/FloatingControlService.kt')
floating = float_path.read_text(encoding='utf-8')

if 'AARISH_AI_AGENT_BUTTON_FIELD_V1' not in floating:
    field_anchor = '''    private lateinit var btnAiWait: Button\n'''
    field = '''    private lateinit var btnAgent: Button // AARISH_AI_AGENT_BUTTON_FIELD_V1\n'''
    floating = replace_once(floating, field_anchor, field_anchor + field, 'agent field')

if 'AARISH_AI_AGENT_BUTTON_V1' not in floating:
    button_anchor = '''    // AARISH_AI_WAIT_BUTTON_V1_PANEL\n    btnAiWait = Button(this).apply {\n        text = "AI"\n        contentDescription = "Record AI Wait step"\n        setOnClickListener { recordWaitAiAction() }\n        visibility = View.GONE\n    }\n'''
    button = '''\n    // AARISH_AI_AGENT_BUTTON_V1\n    btnAgent = Button(this).apply {\n        text = "🤖"\n        contentDescription = "Autonomous AI Mission"\n        isAllCaps = false\n        setOnClickListener {\n            if (AutoActionService.isAiAgentRunning()) {\n                AutoActionService.stopAiAgent(this@FloatingControlService)\n                Toast.makeText(this@FloatingControlService, "AI agent stopped", Toast.LENGTH_SHORT).show()\n            } else {\n                showAiMissionDialogV1()\n            }\n        }\n        setOnLongClickListener {\n            Toast.makeText(this@FloatingControlService, "AI Mission: prompt do; recording optional hai", Toast.LENGTH_LONG).show()\n            true\n        }\n        visibility = View.VISIBLE\n    }\n'''
    floating = replace_once(floating, button_anchor, button_anchor + button, 'agent button')

if 'root.addView(btnAgent)' not in floating:
    add_anchor = '''    root.addView(btnAiWait)\n'''
    floating = replace_once(floating, add_anchor, add_anchor + '''    root.addView(btnAgent)\n''', 'agent root add')

if 'AARISH_AI_MISSION_DIALOG_V1' not in floating:
    method_anchor = '''private fun recordWaitAiAction() {\n'''
    method = r'''// AARISH_AI_MISSION_DIALOG_V1
private fun showAiMissionDialogV1() {
    var provider = "AUTO"

    val input = android.widget.EditText(this).apply {
        hint = "Kya kaam karwana hai? Example: ChatGPT kholo, latest photo attach karo aur answer Notes me save karo"
        minLines = 3
        maxLines = 8
        setPadding(dp(12), dp(10), dp(12), dp(10))
        setTextColor(android.graphics.Color.WHITE)
        setHintTextColor(android.graphics.Color.LTGRAY)
    }

    val providerGroup = android.widget.RadioGroup(this).apply {
        orientation = android.widget.RadioGroup.HORIZONTAL
        gravity = android.view.Gravity.CENTER
    }
    listOf("AUTO", "CHATGPT", "GEMINI").forEachIndexed { index, name ->
        providerGroup.addView(android.widget.RadioButton(this).apply {
            id = 7100 + index
            text = name
            setTextColor(android.graphics.Color.WHITE)
            isChecked = name == "AUTO"
            setOnCheckedChangeListener { _, checked -> if (checked) provider = name }
        })
    }

    val box = android.widget.LinearLayout(this).apply {
        orientation = android.widget.LinearLayout.VERTICAL
        setPadding(dp(12), dp(8), dp(12), dp(8))
        addView(android.widget.TextView(this@FloatingControlService).apply {
            text = "Prompt-only autonomous mode • recording ki zaroorat nahi.\nAI sirf next bounded action choose karega; app execute + verify karega."
            setTextColor(android.graphics.Color.LTGRAY)
            textSize = 12f
            setPadding(0, 0, 0, dp(8))
        })
        addView(input, android.widget.LinearLayout.LayoutParams(
            android.view.ViewGroup.LayoutParams.MATCH_PARENT,
            android.view.ViewGroup.LayoutParams.WRAP_CONTENT
        ))
        addView(providerGroup)
    }

    val dialog = android.app.AlertDialog.Builder(this, android.R.style.Theme_Material_Dialog_Alert)
        .setTitle("🤖 Autonomous Mission")
        .setView(box)
        .setPositiveButton("START", null)
        .setNegativeButton("Cancel", null)
        .create()

    dialog.setOnShowListener {
        dialog.getButton(android.app.AlertDialog.BUTTON_POSITIVE)?.setOnClickListener {
            val goal = input.text?.toString().orEmpty().trim()
            if (goal.isBlank()) {
                input.error = "Prompt likho"
                return@setOnClickListener
            }
            val started = AutoActionService.startAutonomousMission(this, goal, provider)
            if (started) {
                dialog.dismiss()
                Toast.makeText(this, "🤖 Mission started • $provider", Toast.LENGTH_SHORT).show()
            }
        }
    }

    showOverlayDialogSafely(dialog)
}

'''
    floating = replace_once(floating, method_anchor, method + method_anchor, 'mission dialog')

float_path.write_text(floating, encoding='utf-8')
print('AI sidecar integration patch applied.')
