import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';

/// Speaks text with the device's own TTS engine (Google TTS on most Android phones).
/// `speak` returns right away; "complete" / "cancel" / "error" events report the result,
/// so long texts never hit a call timeout on the Python side.
class TtsService extends FletService {
  TtsService({required super.control});

  final FlutterTts tts = FlutterTts();

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_invokeMethod);
    tts.awaitSpeakCompletion(false);
    tts.setCompletionHandler(() => control.triggerEvent("complete"));
    tts.setCancelHandler(() => control.triggerEvent("cancel"));
    tts.setErrorHandler((msg) => control.triggerEvent("error", "$msg"));
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    debugPrint("Tts.$name($args)");
    switch (name) {
      case "speak":
        await tts.setLanguage(args["language"] ?? "he-IL");
        final voice = args["voice"];
        if (voice is Map && voice["name"] != null) {
          await tts.setVoice({
            "name": "${voice["name"]}",
            "locale": "${voice["locale"] ?? args["language"] ?? "he-IL"}",
          });
        }
        await tts.setSpeechRate((args["rate"] ?? 0.5).toDouble());
        await tts.setPitch((args["pitch"] ?? 1.0).toDouble());
        return await tts.speak(args["text"] ?? "");
      case "stop":
        return await tts.stop();
      case "is_language_available":
        return await tts.isLanguageAvailable(args["language"] ?? "he-IL");
      case "get_voices":
        final voices = await tts.getVoices;
        return (voices as List? ?? [])
            .map((v) => Map<String, dynamic>.from(v as Map))
            .toList();
      case "max_input_length":
        return await tts.getMaxSpeechInputLength;
      default:
        throw Exception("Unknown Tts method: $name");
    }
  }

  @override
  void dispose() {
    control.removeInvokeMethodListener(_invokeMethod);
    tts.stop();
    super.dispose();
  }
}
