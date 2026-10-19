import 'package:flet/flet.dart';

import 'tts.dart';

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "Tts":
        return TtsService(control: control);
      default:
        return null;
    }
  }
}
