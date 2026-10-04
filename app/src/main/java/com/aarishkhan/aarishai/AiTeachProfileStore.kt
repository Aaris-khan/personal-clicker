package com.aarishkhan.aarishai

import android.content.Context
import org.json.JSONObject
import java.util.Locale

/**
 * AARISH_UNIVERSAL_AI_TEACH_PROFILE_V3
 *
 * Stores only compact structural fingerprints for provider controls learned from the user.
 * No screenshots, prompts, AI replies, or long surrounding conversation text are persisted.
 */
object AiTeachProfileStore {
    const val ROLE_SEND = "SEND"
    const val ROLE_COPY = "COPY"

    private const val PREF = "aarish_ai_teach_profiles_v3"
    private const val VERSION = 3

    data class ControlFingerprint(
        val text: String = "",
        val desc: String = "",
        val viewId: String = "",
        val className: String = "",
        val treePath: String = "",
        val roleFlags: String = "",
        val xPercent: Float = Float.NaN,
        val yPercent: Float = Float.NaN,
        val wPercent: Float = 0f,
        val hPercent: Float = 0f
    )

    data class ProviderProfile(
        val packageName: String,
        val send: ControlFingerprint? = null,
        val copy: ControlFingerprint? = null,
        val updatedAt: Long = 0L,
        val version: Int = VERSION
    ) {
        val ready: Boolean get() = send != null && copy != null
    }

    private fun prefs(context: Context) =
        context.getSharedPreferences(PREF, Context.MODE_PRIVATE)

    private fun cleanPackage(raw: String): String =
        raw.trim().take(220).takeIf {
            it.matches(Regex("^[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z][A-Za-z0-9_]*)+$"))
        }.orEmpty()

    private fun cleanLabel(raw: String?): String = raw.orEmpty()
        .replace(Regex("[\\u0000-\\u001F]+"), " ")
        .replace(Regex("\\s+"), " ")
        .trim()
        .take(160)

    private fun cleanPath(raw: String?): String = raw.orEmpty()
        .replace(Regex("[\\u0000-\\u001F]+"), " ")
        .trim()
        .take(600)

    private fun normalized(value: Float): Float =
        if (value.isNaN() || value.isInfinite() || value !in 0f..1f) Float.NaN else value

    private fun nonNegative(value: Float): Float =
        if (value.isNaN() || value.isInfinite()) 0f else value.coerceIn(0f, 1f)

    fun fingerprint(snapshot: TargetSnapshot): ControlFingerprint = ControlFingerprint(
        text = cleanLabel(snapshot.targetText),
        desc = cleanLabel(snapshot.targetDesc),
        viewId = cleanLabel(snapshot.targetId),
        className = cleanLabel(snapshot.targetClass),
        treePath = cleanPath(snapshot.targetTreePath),
        roleFlags = cleanLabel(snapshot.targetRoleFlags),
        xPercent = normalized(snapshot.xPercent),
        yPercent = normalized(snapshot.yPercent),
        wPercent = nonNegative(snapshot.targetWPercent),
        hPercent = nonNegative(snapshot.targetHPercent)
    )

    private fun fpToJson(fp: ControlFingerprint): JSONObject = JSONObject().apply {
        put("text", fp.text)
        put("desc", fp.desc)
        put("viewId", fp.viewId)
        put("className", fp.className)
        put("treePath", fp.treePath)
        put("roleFlags", fp.roleFlags)
        if (!fp.xPercent.isNaN()) put("xPercent", fp.xPercent.toDouble())
        if (!fp.yPercent.isNaN()) put("yPercent", fp.yPercent.toDouble())
        put("wPercent", fp.wPercent.toDouble())
        put("hPercent", fp.hPercent.toDouble())
    }

    private fun fpFromJson(obj: JSONObject?): ControlFingerprint? {
        val o = obj ?: return null
        val x = if (o.has("xPercent")) o.optDouble("xPercent", Double.NaN).toFloat() else Float.NaN
        val y = if (o.has("yPercent")) o.optDouble("yPercent", Double.NaN).toFloat() else Float.NaN
        val fp = ControlFingerprint(
            text = cleanLabel(o.optString("text", "")),
            desc = cleanLabel(o.optString("desc", "")),
            viewId = cleanLabel(o.optString("viewId", "")),
            className = cleanLabel(o.optString("className", "")),
            treePath = cleanPath(o.optString("treePath", "")),
            roleFlags = cleanLabel(o.optString("roleFlags", "")),
            xPercent = normalized(x),
            yPercent = normalized(y),
            wPercent = nonNegative(o.optDouble("wPercent", 0.0).toFloat()),
            hPercent = nonNegative(o.optDouble("hPercent", 0.0).toFloat())
        )
        val structuralSignal = listOf(fp.text, fp.desc, fp.viewId, fp.className, fp.treePath, fp.roleFlags)
            .any { it.isNotBlank() }
        return fp.takeIf { structuralSignal || (!fp.xPercent.isNaN() && !fp.yPercent.isNaN()) }
    }

    private fun key(pkg: String) = "profile_${pkg.lowercase(Locale.US)}"

    fun load(context: Context, packageName: String): ProviderProfile? {
        val pkg = cleanPackage(packageName)
        if (pkg.isBlank()) return null
        val raw = prefs(context).getString(key(pkg), null).orEmpty()
        if (raw.isBlank()) return null
        return try {
            val o = JSONObject(raw)
            if (o.optInt("version", 0) != VERSION) return null
            ProviderProfile(
                packageName = pkg,
                send = fpFromJson(o.optJSONObject("send")),
                copy = fpFromJson(o.optJSONObject("copy")),
                updatedAt = o.optLong("updatedAt", 0L),
                version = VERSION
            )
        } catch (_: Throwable) {
            null
        }
    }

    fun role(context: Context, packageName: String, role: String): ControlFingerprint? {
        val p = load(context, packageName) ?: return null
        return when (role.trim().uppercase(Locale.US)) {
            ROLE_SEND -> p.send
            ROLE_COPY -> p.copy
            else -> null
        }
    }

    fun saveVerifiedRole(
        context: Context,
        packageName: String,
        role: String,
        snapshot: TargetSnapshot
    ): Boolean {
        val pkg = cleanPackage(packageName)
        val normalizedRole = role.trim().uppercase(Locale.US)
        if (pkg.isBlank() || normalizedRole !in setOf(ROLE_SEND, ROLE_COPY)) return false
        if (!snapshot.targetPackage.orEmpty().equals(pkg, ignoreCase = true)) return false

        val fp = fingerprint(snapshot)
        val old = load(context, pkg)
        val updated = ProviderProfile(
            packageName = pkg,
            send = if (normalizedRole == ROLE_SEND) fp else old?.send,
            copy = if (normalizedRole == ROLE_COPY) fp else old?.copy,
            updatedAt = System.currentTimeMillis(),
            version = VERSION
        )
        val out = JSONObject().apply {
            put("version", VERSION)
            put("packageName", pkg)
            put("updatedAt", updated.updatedAt)
            updated.send?.let { put("send", fpToJson(it)) }
            updated.copy?.let { put("copy", fpToJson(it)) }
        }
        return prefs(context).edit().putString(key(pkg), out.toString()).commit()
    }

    fun isReady(context: Context, packageName: String): Boolean =
        load(context, packageName)?.ready == true

    fun clear(context: Context, packageName: String): Boolean {
        val pkg = cleanPackage(packageName)
        if (pkg.isBlank()) return false
        return prefs(context).edit().remove(key(pkg)).commit()
    }
}
