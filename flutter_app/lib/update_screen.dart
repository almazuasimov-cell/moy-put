/// Экран обновления приложения — in-app установка через MethodChannel
import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import 'config.dart';
import 'api_service.dart';

class UpdateScreen extends StatefulWidget {
  final Map<String, dynamic> updateInfo;
  final bool forceUpdate;

  const UpdateScreen({
    super.key,
    required this.updateInfo,
    this.forceUpdate = false,
  });

  @override
  State<UpdateScreen> createState() => _UpdateScreenState();
}

class _UpdateScreenState extends State<UpdateScreen> with WidgetsBindingObserver {
  static const _channel = MethodChannel('com.almaz.moy_put/installer');

  bool _downloading = false;
  double _downloadProgress = 0;
  bool _installing = false;
  bool _installFailed = false;
  bool _needsPermission = false;
  String? _savedApkPath;
  String? _errorMessage;

  StreamSubscription<List<int>>? _downloadSubscription;
  IOSink? _downloadSink;
  http.Client? _downloadClient;

  String get _version => widget.updateInfo['version'] ?? '';
  String get _changelog => widget.updateInfo['changelog'] ?? '';
  String get _apkUrl => widget.updateInfo['apk_url'] ?? '';
  bool get _isRequired => widget.updateInfo['is_required'] == true || widget.forceUpdate;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    _downloadSubscription?.cancel();
    _downloadSink?.close().catchError((_) {});
    _downloadClient?.close();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      if (_needsPermission && _savedApkPath != null) {
        _checkPermissionAndInstall();
      } else if (_installing) {
        _verifyInstallation();
      }
    }
  }

  Future<void> _verifyInstallation() async {
    if (!mounted) return;
    setState(() => _installing = false);

    try {
      final info = await PackageInfo.fromPlatform();
      final currentCode = int.tryParse(info.buildNumber) ?? 0;
      final serverCode = widget.updateInfo['version_code'] ?? 0;

      if (currentCode >= serverCode) {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setInt(AppConfig.installedVersionKey, serverCode);
        if (mounted) Navigator.of(context).pushReplacementNamed('/');
        return;
      }
    } catch (_) {}

    if (mounted) {
      setState(() {
        _installFailed = true;
        _errorMessage = 'Не удалось установить. Попробуйте через браузер.';
      });
    }
  }

  Future<bool> _canRequestInstall() async {
    try {
      final result = await _channel.invokeMethod<bool>('canRequestInstall');
      return result ?? false;
    } catch (_) {
      return true;
    }
  }

  Future<void> _openInstallSettings() async {
    try {
      await _channel.invokeMethod('openInstallSettings');
    } catch (_) {}
  }

  Future<void> _checkPermissionAndInstall() async {
    if (!mounted) return;
    setState(() => _needsPermission = false);

    final canInstall = await _canRequestInstall();
    if (canInstall) {
      await _doInstall();
    } else {
      if (!mounted) return;
      setState(() => _needsPermission = true);
    }
  }

  Future<void> _downloadUpdate() async {
    if (_apkUrl.isEmpty) {
      setState(() => _errorMessage = 'Нет ссылки на APK');
      return;
    }

    setState(() {
      _downloading = true;
      _errorMessage = null;
      _savedApkPath = null;
      _needsPermission = false;
      _installFailed = false;
    });

    try {
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}/moy_put_update.apk');
      if (await file.exists()) await file.delete();

      final client = http.Client();
      _downloadClient = client;
      final request = http.Request('GET', Uri.parse(_apkUrl));
      final response = await client.send(request);

      if (response.statusCode != 200) {
        throw Exception('Ошибка сервера: ${response.statusCode}');
      }

      final contentLength = response.contentLength ?? 0;
      int received = 0;
      final sink = file.openWrite();
      _downloadSink = sink;

      final completer = Completer<void>();
      _downloadSubscription = response.stream.listen(
        (chunk) {
          sink.add(chunk);
          received += chunk.length;
          if (contentLength > 0 && mounted) {
            setState(() => _downloadProgress = received / contentLength);
          }
        },
        onDone: () => completer.complete(),
        onError: (e) => completer.completeError(e),
        cancelOnError: true,
      );
      await completer.future;

      await sink.close();
      client.close();
      _downloadSubscription = null;
      _downloadSink = null;
      _downloadClient = null;

      if (!await file.exists() || await file.length() == 0) {
        throw Exception('Файл не загрузился');
      }

      _savedApkPath = file.path;

      final canInstall = await _canRequestInstall();
      if (!canInstall) {
        if (!mounted) return;
        setState(() {
          _downloading = false;
          _needsPermission = true;
        });
        return;
      }

      await _doInstall();
    } catch (e) {
      _errorMessage = e.toString();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Ошибка: ${e.toString().replaceAll('Exception: ', '')}'),
            backgroundColor: Colors.red,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
    if (!mounted) return;
    setState(() {
      _downloading = false;
      _installing = false;
    });
  }

  Future<void> _doInstall() async {
    if (_savedApkPath == null) return;

    setState(() {
      _installing = true;
      _installFailed = false;
      _errorMessage = null;
    });

    try {
      await _channel.invokeMethod('installApk', {'filePath': _savedApkPath});
    } catch (e) {
      if (!mounted) return;
      setState(() => _installing = false);
      _installFailed = true;
      _errorMessage = 'Автоустановка не сработала. Скачайте через браузер.';
    }
  }

  Future<void> _retryInstall() async {
    if (_savedApkPath == null) {
      _downloadUpdate();
      return;
    }
    final file = File(_savedApkPath!);
    if (!await file.exists()) {
      _downloadUpdate();
      return;
    }

    final canInstall = await _canRequestInstall();
    if (!canInstall) {
      if (!mounted) return;
      setState(() => _needsPermission = true);
      return;
    }

    setState(() {
      _installFailed = false;
      _errorMessage = null;
    });
    await _doInstall();
  }

  void _openBrowserDownload() {
    launchUrl(Uri.parse(_apkUrl), mode: LaunchMode.externalApplication);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final apkExists = _savedApkPath != null && File(_savedApkPath!).existsSync();

    return PopScope(
      canPop: !_isRequired,
      child: Scaffold(
        appBar: _isRequired
            ? null
            : AppBar(title: const Text('Обновление')),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  width: 100, height: 100,
                  decoration: BoxDecoration(
                    color: _installFailed
                        ? Colors.red.withValues(alpha: 0.1)
                        : _isRequired
                            ? Colors.orange.withValues(alpha: 0.1)
                            : cs.primary.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(24),
                  ),
                  child: Icon(
                    _installFailed
                        ? Icons.error_outline_rounded
                        : _isRequired
                            ? Icons.warning_amber_rounded
                            : Icons.system_update_rounded,
                    size: 50,
                    color: _installFailed
                        ? Colors.red
                        : _isRequired
                            ? Colors.orange
                            : cs.primary,
                  ),
                ),
                const SizedBox(height: 24),
                Text(
                  _installFailed
                      ? 'Установка не удалась'
                      : _isRequired
                          ? 'Обязательное обновление'
                          : 'Доступно обновление',
                  style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                  decoration: BoxDecoration(
                    color: Colors.grey.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    'Версия $_version',
                    style: TextStyle(fontWeight: FontWeight.w600, color: cs.onSurface.withValues(alpha: 0.75)),
                  ),
                ),
                if (_changelog.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.grey.withValues(alpha: 0.05),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Что нового:', style: TextStyle(fontWeight: FontWeight.bold)),
                        const SizedBox(height: 4),
                        Text(_changelog, style: TextStyle(color: cs.onSurface.withValues(alpha: 0.65))),
                      ],
                    ),
                  ),
                ],
                if (_installFailed) ...[
                  const SizedBox(height: 16),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.red.withValues(alpha: 0.05),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: Colors.red.withValues(alpha: 0.2)),
                    ),
                    child: Column(
                      children: [
                        const Text('Автоустановка не сработала', textAlign: TextAlign.center,
                            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                        const SizedBox(height: 8),
                        Text('На некоторых устройствах (Xiaomi, Huawei) нужно разрешить установку из браузера.',
                            textAlign: TextAlign.center,
                            style: TextStyle(color: cs.onSurface.withValues(alpha: 0.65), fontSize: 13)),
                      ],
                    ),
                  ),
                ],
                const SizedBox(height: 24),
                if (_downloading) ...[
                  ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: LinearProgressIndicator(value: _downloadProgress, minHeight: 8),
                  ),
                  const SizedBox(height: 8),
                  Text('${(_downloadProgress * 100).toStringAsFixed(0)}%',
                      style: TextStyle(color: cs.onSurface.withValues(alpha: 0.65))),
                ],
                if (_installing) ...[
                  const SizedBox(height: 16),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2)),
                      const SizedBox(width: 12),
                      Expanded(child: Text('Открываем установщик...',
                          style: TextStyle(color: cs.onSurface.withValues(alpha: 0.65)))),
                    ],
                  ),
                  const SizedBox(height: 16),
                  SizedBox(
                    width: double.infinity, height: 48,
                    child: FilledButton.icon(
                      onPressed: () {
                        setState(() => _installing = false);
                        _verifyInstallation();
                      },
                      icon: const Icon(Icons.check_circle_outline_rounded),
                      label: const Text('Я установил', style: TextStyle(fontSize: 15)),
                      style: FilledButton.styleFrom(
                        backgroundColor: cs.primary,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  SizedBox(
                    width: double.infinity, height: 44,
                    child: OutlinedButton.icon(
                      onPressed: _openBrowserDownload,
                      icon: const Icon(Icons.open_in_browser_rounded, size: 20),
                      label: const Text('Скачать через браузер', style: TextStyle(fontSize: 14)),
                      style: OutlinedButton.styleFrom(
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                    ),
                  ),
                ],
                if (_needsPermission) ...[
                  const SizedBox(height: 16),
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.orange.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: Colors.orange.withValues(alpha: 0.3)),
                    ),
                    child: Column(
                      children: [
                        const Icon(Icons.security, color: Colors.orange, size: 32),
                        const SizedBox(height: 8),
                        const Text('Нужно разрешение', textAlign: TextAlign.center,
                            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
                        const SizedBox(height: 4),
                        Text('Разрешите установку из неизвестных источников для этого приложения.',
                            textAlign: TextAlign.center,
                            style: TextStyle(color: cs.onSurface.withValues(alpha: 0.65), fontSize: 13)),
                        const SizedBox(height: 16),
                        SizedBox(
                          width: double.infinity, height: 48,
                          child: FilledButton.icon(
                            onPressed: _openInstallSettings,
                            icon: const Icon(Icons.settings_rounded),
                            label: const Text('Открыть настройки'),
                            style: FilledButton.styleFrom(
                              backgroundColor: Colors.orange,
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
                if (!_downloading && !_installing && !_needsPermission) ...[
                  if (_installFailed) ...[
                    SizedBox(
                      width: double.infinity, height: 52,
                      child: FilledButton.icon(
                        onPressed: _openBrowserDownload,
                        icon: const Icon(Icons.open_in_browser_rounded),
                        label: const Text('Скачать через браузер', style: TextStyle(fontSize: 16)),
                        style: FilledButton.styleFrom(
                          backgroundColor: cs.primary,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        ),
                      ),
                    ),
                    if (apkExists) ...[
                      const SizedBox(height: 12),
                      SizedBox(
                        width: double.infinity, height: 48,
                        child: OutlinedButton.icon(
                          onPressed: _retryInstall,
                          icon: const Icon(Icons.replay_rounded),
                          label: const Text('Попробовать снова', style: TextStyle(fontSize: 14)),
                          style: OutlinedButton.styleFrom(
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                          ),
                        ),
                      ),
                    ],
                  ] else ...[
                    if (apkExists) ...[
                      SizedBox(
                        width: double.infinity, height: 52,
                        child: FilledButton.icon(
                          onPressed: _retryInstall,
                          icon: const Icon(Icons.replay_rounded),
                          label: const Text('Установить', style: TextStyle(fontSize: 16)),
                          style: FilledButton.styleFrom(
                            backgroundColor: cs.primary,
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      SizedBox(
                        width: double.infinity, height: 52,
                        child: OutlinedButton.icon(
                          onPressed: _downloadUpdate,
                          icon: const Icon(Icons.download_rounded),
                          label: const Text('Скачать заново', style: TextStyle(fontSize: 16)),
                          style: OutlinedButton.styleFrom(
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                          ),
                        ),
                      ),
                    ] else ...[
                      SizedBox(
                        width: double.infinity, height: 52,
                        child: FilledButton.icon(
                          onPressed: _downloadUpdate,
                          icon: const Icon(Icons.download_rounded),
                          label: const Text('Скачать и установить', style: TextStyle(fontSize: 16)),
                          style: FilledButton.styleFrom(
                            backgroundColor: _isRequired ? Colors.orange : cs.primary,
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                          ),
                        ),
                      ),
                    ],
                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity, height: 48,
                      child: OutlinedButton.icon(
                        onPressed: _openBrowserDownload,
                        icon: const Icon(Icons.open_in_browser_rounded, size: 20),
                        label: const Text('Скачать через браузер', style: TextStyle(fontSize: 14)),
                        style: OutlinedButton.styleFrom(
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                          side: BorderSide(color: Colors.grey.withValues(alpha: 0.3)),
                        ),
                      ),
                    ),
                  ],
                  if (!_isRequired) ...[
                    const SizedBox(height: 12),
                    TextButton(
                      onPressed: () async {
                        final prefs = await SharedPreferences.getInstance();
                        await prefs.setInt(AppConfig.skippedVersionKey,
                            widget.updateInfo['version_code'] ?? 0);
                        if (mounted) Navigator.of(context).pushReplacementNamed('/');
                      },
                      child: const Text('Позже'),
                    ),
                  ],
                  if (_isRequired && _installFailed) ...[
                    const SizedBox(height: 12),
                    TextButton(
                      onPressed: () async {
                        final prefs = await SharedPreferences.getInstance();
                        await prefs.setInt(AppConfig.skippedVersionKey,
                            widget.updateInfo['version_code'] ?? 0);
                        if (mounted) Navigator.of(context).pushReplacementNamed('/');
                      },
                      child: const Text('Всё равно пропустить'),
                    ),
                  ],
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
