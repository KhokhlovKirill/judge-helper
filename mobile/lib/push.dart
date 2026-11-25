import 'dart:async';
import 'dart:io';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'client.dart';

class PushDelivery {
  static StreamSubscription<String>? rotation;
  static String? token;
  static Future<void> attach(Client c) async {
    const project = String.fromEnvironment('FCM_PROJECT');
    if (project.isEmpty || c.email.isEmpty) return;
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp(
        options: FirebaseOptions(
          apiKey: const String.fromEnvironment('FCM_API_KEY'),
          appId: const String.fromEnvironment('FCM_APP_ID'),
          messagingSenderId: const String.fromEnvironment('FCM_SENDER'),
          projectId: project,
          iosBundleId: 'ru.judgehelper.judgeHelper',
        ),
      );
    }
    final f = FirebaseMessaging.instance;
    await f.requestPermission();
    if (Platform.isIOS) {
      await f.setForegroundNotificationPresentationOptions(
        alert: true,
        badge: true,
        sound: true,
      );
      if (await f.getAPNSToken() == null) return;
    }
    Future<void> register(String value) async {
      await c.api('/device', method: 'PUT', data: {'token': value});
      token = value;
    }

    final value = await f.getToken();
    if (value != null) await register(value);
    await rotation?.cancel();
    rotation = f.onTokenRefresh.listen(register);
  }

  static Future<void> detach(Client c) async {
    await rotation?.cancel();
    if (token != null) {
      await c.api('/device', method: 'DELETE', data: {'token': token});
    }
    token = null;
  }
}
