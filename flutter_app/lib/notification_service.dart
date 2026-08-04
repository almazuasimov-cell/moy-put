/// Локальные push-уведомления — ежедневные напоминания
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:timezone/timezone.dart' as tz;
import 'package:timezone/data/latest.dart' as tz_data;

class NotificationService {
  static final _plugin = FlutterLocalNotificationsPlugin();
  static const _reminderKey = 'reminder_enabled';
  static const _reminderTimeKey = 'reminder_time_hour';

  /// Инициализация (вызвать при старте приложения)
  static Future<void> init() async {
    tz_data.initializeTimeZones();
    const androidSettings = AndroidInitializationSettings('@mipmap/ic_launcher');
    const iosSettings = DarwinInitializationSettings(
      requestAlertPermission: true,
      requestBadgePermission: true,
      requestSoundPermission: true,
    );
    await _plugin.initialize(
      const InitializationSettings(android: androidSettings, iOS: iosSettings),
    );
  }

  /// Включить/выключить ежедневное напоминание
  static Future<void> setReminderEnabled(bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_reminderKey, enabled);
    if (enabled) {
      await _scheduleDaily();
    } else {
      await _plugin.cancelAll();
    }
  }

  /// Проверить, включено ли напоминание
  static Future<bool> isReminderEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_reminderKey) ?? false;
  }

  /// Установить время напоминания (час, 0-23)
  static Future<void> setReminderTime(int hour) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_reminderTimeKey, hour);
    if (await isReminderEnabled()) {
      await _scheduleDaily();
    }
  }

  /// Получить время напоминания
  static Future<int> getReminderTime() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getInt(_reminderTimeKey) ?? 21;
  }

  /// Запланировать ежедневное уведомление
  static Future<void> _scheduleDaily() async {
    await _plugin.cancelAll();
    final hour = await getReminderTime();

    const androidDetails = AndroidNotificationDetails(
      'daily_reminder',
      'Ежедневное напоминание',
      channelDescription: 'Напоминание записать дневник',
      importance: Importance.defaultImportance,
      priority: Priority.defaultPriority,
    );
    const iosDetails = DarwinNotificationDetails();

    final now = tz.TZDateTime.now(tz.local);
    var scheduled = tz.TZDateTime(tz.local, now.year, now.month, now.day, hour, 0, 0);
    if (scheduled.isBefore(now)) {
      scheduled = scheduled.add(const Duration(days: 1));
    }

    await _plugin.zonedSchedule(
      0,
      'Время для дневника 📝',
      'Как прошёл твой день? Запиши свои мысли в «Мой путь».',
      scheduled,
      const NotificationDetails(android: androidDetails, iOS: iosDetails),
      androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
      matchDateTimeComponents: DateTimeComponents.time,
      uiLocalNotificationDateInterpretation: UILocalNotificationDateInterpretation.absoluteTime,
    );
  }
}
