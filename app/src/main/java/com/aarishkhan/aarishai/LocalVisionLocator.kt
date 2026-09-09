package com.aarishkhan.aarishai

import android.content.Context
import android.graphics.Bitmap
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.URL
import java.util.Locale
import java.util.concurrent.Executors
import kotlin.math.max

/**
 * Local-only visual target locator.
 *
 * The model is intentionally not allowed to execute actions. It only returns a bounded
 * visual suggestion (normalized x/y + confidence). AutoActionService remains the sole
 * authority that can validate playback state and dispatch a click.
 *
 * Default transport is an OpenAI-compatible llama.cpp server running on the SAME PHONE:
 *   http://127.0.0.1:8080/v1/chat/completions
 *
 * No cloud host is accepted by this class.
 */
object LocalVisionLocator {

    data class VisionTarget(
        val found: Boolean,
        val xPercent: Float,
        val yPercent: Float,
        val confidence: Float,
        val scroll: String,
        val reason: String
    )

    private const val PREFS = "aarish_local_vision_v1"
    private const val KEY_ENABLED = "enabled"
    private const val KEY_ENDPOINT = "endpoint"
    private const val KEY_MODEL = "model"
    private const val KEY_MIN_CONFIDENCE = "min_confidence"

    private const val DEFAULT_ENDPOINT = "http://127.0.0.1:8080/v1/chat/completions"
    private const val DEFAULT_MODEL = "local-vision"
    private const val DEFAULT_MIN_CONFIDENCE = 0.72f

    private val executor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "AarishLocalVision").apply { isDaemon = true }
    }

    fun isEnabled(context: Context): Boolean {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getBoolean(KEY_ENABLED, true)
    }

    fun locate(
        context: Context,
        bitmap: Bitmap,
        gesture: RecordedGesture,
        callback: (VisionTarget?) -> Unit
    ) {
        if (!isEnabled(context)) {
            try { bitmap.recycle() } catch (_: Throwable) {}
            callback(null)
            return
        }

        executor.execute {
            val result = try {
                locateBlocking(context, bitmap, gesture)
            } catch (_: Throwable) {
                null
            } finally {
                try { bitmap.recycle() } catch (_: Throwable) {}
            }
            callback(result)
        }
    }

    private fun locateBlocking(
        context: Context,
        bitmap: Bitmap,
        gesture: RecordedGesture
    ): VisionTarget? {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val endpoint = prefs.getString(KEY_ENDPOINT, DEFAULT_ENDPOINT)
            ?.trim()
            ?.ifBlank { DEFAULT_ENDPOINT }
            ?: DEFAULT_ENDPOINT
        val model = prefs.getString(KEY_MODEL, DEFAULT_MODEL)
            ?.trim()
            ?.ifBlank { DEFAULT_MODEL }
            ?: DEFAULT_MODEL
        val minConfidence = prefs.getFloat(KEY_MIN_CONFIDENCE, DEFAULT_MIN_CONFIDENCE)
            .coerceIn(0.50f, 0.98f)

        if (!isStrictLoopbackUrl(endpoint)) return null

        val encoded = encodeScreenshot(bitmap) ?: return null
        val prompt = buildPrompt(gesture, encoded.width, encoded.height)
        val request = JSONObject().apply {
            put("model", model)
            put("temperature", 0)
            put("max_tokens", 220)
            put("messages", JSONArray().put(
                JSONObject().apply {
                    put("role", "user")
                    put("content", JSONArray().apply {
                        put(JSONObject().apply {
                            put("type", "text")
                            put("text", prompt)
                        })
                        put(JSONObject().apply {
                            put("type", "image_url")
                            put("image_url", JSONObject().put(
                                "url",
                                "data:image/jpeg;base64,${encoded.base64}"
                            ))
                        })
                    })
                }
            ))
        }

        val responseText = postJson(endpoint, request.toString()) ?: return null
        val modelText = extractAssistantText(responseText) ?: return null
        val parsed = parseTarget(modelText, encoded.width, encoded.height) ?: return null
        if (!parsed.found) return parsed
        if (parsed.confidence < minConfidence) return null
        if (parsed.xPercent !in 0f..1f || parsed.yPercent !in 0f..1f) return null
        return parsed
    }

    private data class EncodedScreenshot(
        val base64: String,
        val width: Int,
        val height: Int
    )

    private fun encodeScreenshot(bitmap: Bitmap): EncodedScreenshot? {
        if (bitmap.width <= 0 || bitmap.height <= 0) return null

        // VLM UI localization does not need native phone resolution. Downscaling cuts
        // prompt size, RAM pressure and vision-encoder latency considerably.
        val maxSide = max(bitmap.width, bitmap.height)
        val scale = if (maxSide > 1280) 1280f / maxSide.toFloat() else 1f
        val width = (bitmap.width * scale).toInt().coerceAtLeast(1)
        val height = (bitmap.height * scale).toInt().coerceAtLeast(1)

        val scaled = if (width != bitmap.width || height != bitmap.height) {
            Bitmap.createScaledBitmap(bitmap, width, height, true)
        } else {
            bitmap
        }

        return try {
            val stream = ByteArrayOutputStream()
            if (!scaled.compress(Bitmap.CompressFormat.JPEG, 76, stream)) return null
            val bytes = stream.toByteArray()
            EncodedScreenshot(
                base64 = Base64.encodeToString(bytes, Base64.NO_WRAP),
                width = width,
                height = height
            )
        } finally {
            if (scaled !== bitmap) {
                try { scaled.recycle() } catch (_: Throwable) {}
            }
        }
    }

    private fun buildPrompt(gesture: RecordedGesture, imageW: Int, imageH: Int): String {
        fun clean(value: String?, limit: Int): String {
            return value.orEmpty()
                .replace(Regex("[\\r\\n\\t]+"), " ")
                .replace(Regex("\\s+"), " ")
                .trim()
                .take(limit)
        }

        val oldBounds = if (
            gesture.targetLeft >= 0 && gesture.targetTop >= 0 &&
            gesture.targetRight > gesture.targetLeft && gesture.targetBottom > gesture.targetTop
        ) {
            "${gesture.targetLeft},${gesture.targetTop},${gesture.targetRight},${gesture.targetBottom}"
        } else {
            "unknown"
        }

        return """
You are the visual fallback for an Android automation recorder.
The screenshot is the CURRENT screen. Locate the SAME control the user selected while recording.
Do not choose a merely similar nearby control. Use text, icon meaning, UI context and relative placement together.
If the intended control is not visibly present, return found=false. Never invent coordinates.

RECORDED TARGET:
package=${clean(gesture.targetPackage, 120)}
resource_id=${clean(gesture.targetId, 180)}
text=${clean(gesture.targetText, 180)}
description=${clean(gesture.targetDesc, 180)}
class=${clean(gesture.targetClass, 140)}
role=${clean(gesture.targetRoleFlags, 220)}
context=${clean(gesture.targetContextText, 900)}
child_context=${clean(gesture.targetChildText, 500)}
sibling_context=${clean(gesture.targetSiblingText, 500)}
tree_path=${clean(gesture.targetTreePath, 360)}
recorded_bounds=$oldBounds
recorded_anchor=${gesture.xPercent},${gesture.yPercent}

CURRENT IMAGE SIZE: ${imageW}x${imageH}

Return ONLY one JSON object, no markdown and no explanation outside JSON:
{"found":true,"x":0.0,"y":0.0,"confidence":0.0,"scroll":"none","reason":"short reason"}

Rules:
- x and y MUST be normalized 0..1 coordinates relative to the screenshot.
- Put x/y at the safe clickable center of the intended control.
- confidence is 0..1.
- scroll must be one of: none, up, down.
- If target is not currently visible: {"found":false,"x":0.0,"y":0.0,"confidence":0.0,"scroll":"none","reason":"not visible"}
""".trimIndent()
    }

    private fun isStrictLoopbackUrl(raw: String): Boolean {
        return try {
            val url = URL(raw)
            if (!url.protocol.equals("http", ignoreCase = true) &&
                !url.protocol.equals("https", ignoreCase = true)
            ) return false

            val host = url.host.trim().lowercase(Locale.US)
            if (host == "localhost" || host == "127.0.0.1" || host == "::1" || host == "[::1]") {
                return true
            }

            // Defensive check for alternate textual loopback addresses. DNS names that merely
            // resolve to loopback are intentionally rejected to prevent external redirection.
            val address = InetAddress.getByName(host)
            address.isLoopbackAddress && host.all { it.isDigit() || it == '.' || it == ':' }
        } catch (_: Throwable) {
            false
        }
    }

    private fun postJson(endpoint: String, json: String): String? {
        val connection = (URL(endpoint).openConnection() as? HttpURLConnection) ?: return null
        return try {
            connection.requestMethod = "POST"
            connection.connectTimeout = 1_800
            connection.readTimeout = 12_000
            connection.doInput = true
            connection.doOutput = true
            connection.useCaches = false
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            connection.setRequestProperty("Accept", "application/json")

            connection.outputStream.use { out ->
                out.write(json.toByteArray(Charsets.UTF_8))
                out.flush()
            }

            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (code !in 200..299 || text.isBlank()) null else text
        } catch (_: Throwable) {
            null
        } finally {
            try { connection.disconnect() } catch (_: Throwable) {}
        }
    }

    private fun extractAssistantText(raw: String): String? {
        return try {
            val root = JSONObject(raw)
            val choices = root.optJSONArray("choices") ?: return null
            val first = choices.optJSONObject(0) ?: return null
            val message = first.optJSONObject("message") ?: return null
            val content = message.opt("content")
            when (content) {
                is String -> content
                is JSONArray -> {
                    buildString {
                        for (i in 0 until content.length()) {
                            val item = content.optJSONObject(i) ?: continue
                            val text = item.optString("text", "")
                            if (text.isNotBlank()) append(text)
                        }
                    }.takeIf { it.isNotBlank() }
                }
                else -> null
            }
        } catch (_: Throwable) {
            null
        }
    }

    private fun parseTarget(raw: String, imageW: Int, imageH: Int): VisionTarget? {
        return try {
            val cleaned = raw
                .replace("```json", "", ignoreCase = true)
                .replace("```", "")
                .trim()
            val start = cleaned.indexOf('{')
            val end = cleaned.lastIndexOf('}')
            if (start < 0 || end <= start) return null

            val obj = JSONObject(cleaned.substring(start, end + 1))
            val found = obj.optBoolean("found", false)
            var x = obj.optDouble("x", Double.NaN).toFloat()
            var y = obj.optDouble("y", Double.NaN).toFloat()
            val confidence = obj.optDouble("confidence", 0.0).toFloat().coerceIn(0f, 1f)
            val scroll = obj.optString("scroll", "none")
                .trim()
                .lowercase(Locale.US)
                .let { if (it == "up" || it == "down") it else "none" }
            val reason = obj.optString("reason", "")
                .replace(Regex("\\s+"), " ")
                .trim()
                .take(160)

            if (!found) {
                return VisionTarget(false, 0f, 0f, confidence, scroll, reason)
            }

            if (x.isNaN() || y.isNaN()) return null

            // Be forgiving if a model disobeys the prompt and emits image pixels.
            if (x > 1f && x <= imageW.toFloat()) x /= imageW.toFloat().coerceAtLeast(1f)
            if (y > 1f && y <= imageH.toFloat()) y /= imageH.toFloat().coerceAtLeast(1f)

            if (x !in 0f..1f || y !in 0f..1f) return null
            VisionTarget(true, x, y, confidence, scroll, reason)
        } catch (_: Throwable) {
            null
        }
    }
}
