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

/** Local-only visual target locator. */
object LocalVisionLocator {
    data class VisionTarget(val found:Boolean,val xPercent:Float,val yPercent:Float,val confidence:Float,val scroll:String,val reason:String)
    private const val PREFS="aarish_local_vision_v1"
    private const val KEY_ENABLED="enabled"
    private const val KEY_ENDPOINT="endpoint"
    private const val KEY_MODEL="model"
    private const val KEY_MIN_CONFIDENCE="min_confidence"
    private const val DEFAULT_ENDPOINT="http://127.0.0.1:8080/v1/chat/completions"
    private const val DEFAULT_MODEL="local-vision"
    private const val DEFAULT_MIN_CONFIDENCE=0.72f
    private const val MAX_RESPONSE_CHARS=64*1024
    private val executor=Executors.newSingleThreadExecutor{r->Thread(r,"AarishLocalVision").apply{isDaemon=true}}

    fun isEnabled(context:Context)=context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).getBoolean(KEY_ENABLED,true)
    fun locate(context:Context,bitmap:Bitmap,gesture:RecordedGesture,callback:(VisionTarget?)->Unit){
        if(!isEnabled(context)){try{bitmap.recycle()}catch(_:Throwable){};callback(null);return}
        executor.execute{val result=try{locateBlocking(context,bitmap,gesture)}catch(_:Throwable){null}finally{try{bitmap.recycle()}catch(_:Throwable){}};callback(result)}
    }
    private fun locateBlocking(context:Context,bitmap:Bitmap,gesture:RecordedGesture):VisionTarget?{
        val prefs=context.getSharedPreferences(PREFS,Context.MODE_PRIVATE)
        val endpoint=prefs.getString(KEY_ENDPOINT,DEFAULT_ENDPOINT)?.trim()?.ifBlank{DEFAULT_ENDPOINT}?:DEFAULT_ENDPOINT
        val model=prefs.getString(KEY_MODEL,DEFAULT_MODEL)?.trim()?.ifBlank{DEFAULT_MODEL}?:DEFAULT_MODEL
        val minConfidence=prefs.getFloat(KEY_MIN_CONFIDENCE,DEFAULT_MIN_CONFIDENCE).coerceIn(.50f,.98f)
        if(!isStrictLoopbackUrl(endpoint))return null
        val encoded=encodeScreenshot(bitmap)?:return null
        val request=JSONObject().apply{put("model",model);put("temperature",0);put("max_tokens",220);put("messages",JSONArray().put(JSONObject().apply{put("role","user");put("content",JSONArray().apply{put(JSONObject().apply{put("type","text");put("text",buildPrompt(gesture,encoded.width,encoded.height))});put(JSONObject().apply{put("type","image_url");put("image_url",JSONObject().put("url","data:image/jpeg;base64,${encoded.base64}"))})})}))}
        val parsed=parseTarget(extractAssistantText(postJson(endpoint,request.toString())?:return null)?:return null,encoded.width,encoded.height)?:return null
        if(!parsed.found)return parsed
        if(parsed.confidence<minConfidence||parsed.xPercent !in 0f..1f||parsed.yPercent !in 0f..1f)return null
        return parsed
    }
    private data class EncodedScreenshot(val base64:String,val width:Int,val height:Int)
    private fun encodeScreenshot(bitmap:Bitmap):EncodedScreenshot?{
        if(bitmap.width<=0||bitmap.height<=0)return null
        val scale=if(max(bitmap.width,bitmap.height)>1280)1280f/max(bitmap.width,bitmap.height).toFloat() else 1f
        val w=(bitmap.width*scale).toInt().coerceAtLeast(1);val h=(bitmap.height*scale).toInt().coerceAtLeast(1)
        val scaled=if(w!=bitmap.width||h!=bitmap.height)Bitmap.createScaledBitmap(bitmap,w,h,true)else bitmap
        return try{val out=ByteArrayOutputStream();if(!scaled.compress(Bitmap.CompressFormat.JPEG,76,out))return null;EncodedScreenshot(Base64.encodeToString(out.toByteArray(),Base64.NO_WRAP),w,h)}finally{if(scaled!==bitmap)try{scaled.recycle()}catch(_:Throwable){}}
    }
    private fun buildPrompt(g:RecordedGesture,w:Int,h:Int):String{
        fun clean(v:String?,n:Int)=v.orEmpty().replace(Regex("[\\r\\n\\t]+")," ").replace(Regex("\\s+")," ").trim().take(n)
        val bounds=if(g.targetLeft>=0&&g.targetTop>=0&&g.targetRight>g.targetLeft&&g.targetBottom>g.targetTop)"${g.targetLeft},${g.targetTop},${g.targetRight},${g.targetBottom}" else "unknown"
        return """You are the visual fallback for an Android automation recorder.
The screenshot is the CURRENT screen. Locate the SAME control the user selected while recording.
Do not choose a merely similar nearby control. Use text, icon meaning, UI context and relative placement together.
If the intended control is not visibly present, return found=false. Never invent coordinates.
RECORDED TARGET:
package=${clean(g.targetPackage,120)}
resource_id=${clean(g.targetId,180)}
text=${clean(g.targetText,180)}
description=${clean(g.targetDesc,180)}
class=${clean(g.targetClass,140)}
role=${clean(g.targetRoleFlags,220)}
context=${clean(g.targetContextText,900)}
child_context=${clean(g.targetChildText,500)}
sibling_context=${clean(g.targetSiblingText,500)}
tree_path=${clean(g.targetTreePath,360)}
recorded_bounds=$bounds
recorded_anchor=${g.xPercent},${g.yPercent}
CURRENT IMAGE SIZE: ${w}x${h}
Return ONLY one JSON object, no markdown and no explanation outside JSON:
{"found":true,"x":0.0,"y":0.0,"confidence":0.0,"scroll":"none","reason":"short reason"}
Rules:
- x and y MUST be normalized 0..1 coordinates relative to the screenshot.
- Put x/y at the safe clickable center of the intended control.
- confidence is 0..1.
- scroll must be one of: none, up, down.
- If target is not currently visible: {"found":false,"x":0.0,"y":0.0,"confidence":0.0,"scroll":"none","reason":"not visible"}""".trimIndent()
    }
    private fun isStrictLoopbackUrl(raw:String):Boolean=try{val u=URL(raw);if(!u.protocol.equals("http",true)&&!u.protocol.equals("https",true))false else{val host=u.host.trim().lowercase(Locale.US);if(host=="localhost"||host=="127.0.0.1"||host=="::1"||host=="[::1]")true else{val a=InetAddress.getByName(host);a.isLoopbackAddress&&host.all{it.isDigit()||it=='.'||it==':'}}}}catch(_:Throwable){false}
    private fun postJson(endpoint:String,json:String):String?{
        val c=(URL(endpoint).openConnection() as? HttpURLConnection)?:return null
        return try{
            c.requestMethod="POST";c.instanceFollowRedirects=false;c.connectTimeout=1800;c.readTimeout=12000;c.doInput=true;c.doOutput=true;c.useCaches=false
            c.setRequestProperty("Content-Type","application/json; charset=utf-8");c.setRequestProperty("Accept","application/json")
            c.outputStream.use{it.write(json.toByteArray(Charsets.UTF_8));it.flush()}
            val code=c.responseCode
            val declared=c.contentLengthLong
            if(declared>MAX_RESPONSE_CHARS*4L)return null
            val stream=if(code in 200..299)c.inputStream else c.errorStream
            val text=stream?.bufferedReader(Charsets.UTF_8)?.use{reader->
                val out=StringBuilder(minOf(4096,MAX_RESPONSE_CHARS));val buf=CharArray(4096);var total=0
                while(true){val n=reader.read(buf);if(n<0)break;total+=n;if(total>MAX_RESPONSE_CHARS)return@use null;out.append(buf,0,n)}
                out.toString()
            }?:return null
            if(code !in 200..299||text.isBlank())null else text
        }catch(_:Throwable){null}finally{try{c.disconnect()}catch(_:Throwable){}}
    }
    private fun extractAssistantText(raw:String):String?=try{val root=JSONObject(raw);val first=root.optJSONArray("choices")?.optJSONObject(0)?:return null;val content=first.optJSONObject("message")?.opt("content");when(content){is String->content;is JSONArray->buildString{for(i in 0 until content.length()){val t=content.optJSONObject(i)?.optString("text","").orEmpty();if(t.isNotBlank())append(t)}}.takeIf{it.isNotBlank()};else->null}}catch(_:Throwable){null}
    private fun parseTarget(raw:String,imageW:Int,imageH:Int):VisionTarget?=try{val cleaned=raw.replace("```json","",true).replace("```","").trim();val s=cleaned.indexOf('{');val e=cleaned.lastIndexOf('}');if(s<0||e<=s)return null;val o=JSONObject(cleaned.substring(s,e+1));val found=o.optBoolean("found",false);var x=o.optDouble("x",Double.NaN).toFloat();var y=o.optDouble("y",Double.NaN).toFloat();val conf=o.optDouble("confidence",0.0).toFloat().coerceIn(0f,1f);val scroll=o.optString("scroll","none").trim().lowercase(Locale.US).let{if(it=="up"||it=="down")it else "none"};val reason=o.optString("reason","").replace(Regex("\\s+")," ").trim().take(160);if(!found)return VisionTarget(false,0f,0f,conf,scroll,reason);if(x.isNaN()||y.isNaN())return null;if(x>1f&&x<=imageW.toFloat())x/=imageW.toFloat().coerceAtLeast(1f);if(y>1f&&y<=imageH.toFloat())y/=imageH.toFloat().coerceAtLeast(1f);if(x !in 0f..1f||y !in 0f..1f)return null;VisionTarget(true,x,y,conf,scroll,reason)}catch(_:Throwable){null}
}
