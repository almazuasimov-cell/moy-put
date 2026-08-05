/// «Мой путь» — AI Voice Diary
/// Точка входа приложения
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'api_service.dart';
import 'auth_screen.dart';
import 'home_screen.dart';
import 'onboarding_screen.dart';
import 'update_screen.dart';
import 'notification_service.dart';
import 'config.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(systemNavigationBarColor: Colors.transparent),
  );
  runApp(const MyApp());
}

class MyApp extends StatefulWidget {
  const MyApp({super.key});

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> with WidgetsBindingObserver {
  bool _initialized = false;
  bool _isLoggedIn = false;
  bool _showOnboarding = false;
  Map<String, dynamic>? _updateInfo;
  DateTime? _lastUpdateCheck;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _initApp();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _checkForUpdateOnResume();
    }
  }

  /// Проверка обновления при возврате в приложение (не чаще раза в 5 минут)
  Future<void> _checkForUpdateOnResume() async {
    final now = DateTime.now();
    if (_lastUpdateCheck != null && now.difference(_lastUpdateCheck!).inMinutes < 5) {
      return;
    }
    _lastUpdateCheck = now;
    if (!ApiService.isLoggedIn) return;

    try {
      final serverInfo = await ApiService.checkUpdate();
      if (serverInfo.isEmpty) return;

      final serverCode = serverInfo['version_code'] ?? 0;
      final isRequired = serverInfo['is_required'] == true;

      final packageInfo = await PackageInfo.fromPlatform();
      final localCode = int.tryParse(packageInfo.buildNumber) ?? 0;

      final prefs = await SharedPreferences.getInstance();
      final skipped = prefs.getInt(AppConfig.skippedVersionKey) ?? 0;
      final installed = prefs.getInt(AppConfig.installedVersionKey) ?? 0;

      // Нужно обновление: сервер новее, не установлена, не пропущена
      final needsUpdate = serverCode > localCode
          && installed < serverCode
          && serverCode > skipped;

      if (!needsUpdate) return;

      final version = serverInfo['version'] as String? ?? '';
      final changelog = serverInfo['changelog'] as String? ?? '';

      if (!mounted) return;
      final doUpdate = await showDialog<bool>(
        context: context,
        barrierDismissible: !isRequired,
        builder: (ctx) => PopScope(
          canPop: !isRequired,
          child: AlertDialog(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            title: Row(children: [
              Icon(
                isRequired ? Icons.warning_amber_rounded : Icons.system_update_rounded,
                color: isRequired ? Colors.orange : Theme.of(context).colorScheme.onSurface,
                size: 28,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  isRequired ? 'Обязательное обновление' : 'Доступно обновление',
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
              ),
            ]),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text('Версия $version', style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                ),
                if (changelog.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Text(changelog, style: TextStyle(color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.75), fontSize: 14)),
                ],
              ],
            ),
            actions: [
              if (!isRequired)
                TextButton(
                  onPressed: () => Navigator.of(ctx).pop(false),
                  child: Text('Позже', style: TextStyle(color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.65))),
                ),
              FilledButton.icon(
                onPressed: () => Navigator.of(ctx).pop(true),
                icon: const Icon(Icons.download_rounded, size: 20),
                label: const Text('Обновить'),
                style: FilledButton.styleFrom(
                  backgroundColor: Theme.of(context).colorScheme.primary,
                  foregroundColor: Theme.of(context).colorScheme.onPrimary,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ],
          ),
        ),
      );

      if (doUpdate == true) {
        // Сохраняем skipped_version чтобы диалог не появлялся повторно
        await prefs.setInt(AppConfig.skippedVersionKey, serverCode);
        if (!mounted) return;
        Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => UpdateScreen(updateInfo: serverInfo, forceUpdate: isRequired),
          ),
        );
      } else if (!isRequired) {
        await prefs.setInt(AppConfig.skippedVersionKey, serverCode);
      }
    } catch (_) {}
  }

  Future<void> _initApp() async {
    await ApiService.init();
    await NotificationService.init();
    final prefs = await SharedPreferences.getInstance();
    final onboardingDone = prefs.getBool(AppConfig.onboardingDoneKey) ?? false;

    // Проверка обновления при старте
    Map<String, dynamic>? updateInfo;
    try {
      final info = await PackageInfo.fromPlatform();
      final currentCode = int.tryParse(info.buildNumber) ?? 0;
      final skippedVersion = prefs.getInt(AppConfig.skippedVersionKey) ?? 0;

      final installedVersion = prefs.getInt(AppConfig.installedVersionKey) ?? 0;
      if (installedVersion == 0 || currentCode > installedVersion) {
        await prefs.setInt(AppConfig.installedVersionKey, currentCode);
      }

      final serverInfo = await ApiService.checkUpdate();
      if (serverInfo.isNotEmpty) {
        final serverCode = serverInfo['version_code'] ?? 0;

        if (serverCode > currentCode && serverCode != skippedVersion) {
          updateInfo = serverInfo;
        }
      }
    } catch (_) {}

    if (!mounted) return;
    setState(() {
      _isLoggedIn = ApiService.isLoggedIn;
      _showOnboarding = !onboardingDone && !_isLoggedIn;
      _updateInfo = updateInfo;
      _initialized = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: AppConfig.appName,
      debugShowCheckedModeBanner: false,
      theme: _buildTheme(Brightness.light),
      darkTheme: _buildTheme(Brightness.dark),
      themeMode: ThemeMode.system,
      home: !_initialized
          ? const Scaffold(body: Center(child: CircularProgressIndicator()))
          : _updateInfo != null
              ? UpdateScreen(
                  updateInfo: _updateInfo!,
                  forceUpdate: _updateInfo!['is_required'] ?? false,
                )
              : _showOnboarding
                  ? const OnboardingScreen()
                  : _isLoggedIn
                      ? const HomeScreen()
                      : const AuthScreen(),
    );
  }

  ThemeData _buildTheme(Brightness brightness) {
    final seed = const Color(0xFF6750A4);
    final scheme = ColorScheme.fromSeed(seedColor: seed, brightness: brightness);

    return ThemeData(
      colorScheme: scheme,
      useMaterial3: true,
      fontFamily: null,
      appBarTheme: AppBarTheme(
        centerTitle: false,
        backgroundColor: scheme.surface,
        surfaceTintColor: scheme.surfaceTint,
      ),
      cardTheme: CardThemeData(
        surfaceTintColor: scheme.surfaceTint,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      ),
    );
  }
}
