package dev.eitan.flet_tts;

import io.flutter.embedding.engine.plugins.FlutterPlugin;

/**
 * Intentionally empty: the speaking is done by the flutter_tts plugin.
 * This class only exists so Flutter treats flet_tts as an Android plugin and merges
 * its AndroidManifest.xml (the TTS_SERVICE <queries> entry) into the app.
 */
public class FletTtsPlugin implements FlutterPlugin {
    @Override
    public void onAttachedToEngine(FlutterPluginBinding binding) {
    }

    @Override
    public void onDetachedFromEngine(FlutterPluginBinding binding) {
    }
}
