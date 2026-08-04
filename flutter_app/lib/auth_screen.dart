/// Экран входа/регистрации
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'api_service.dart';
import 'config.dart';
import 'home_screen.dart';
import 'settings_screen.dart';

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  bool _isLogin = true;
  bool _isLoading = false;
  bool _consent = false;
  final _phoneController = TextEditingController();
  final _nameController = TextEditingController();
  final _passwordController = TextEditingController();
  final _apiUrlController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _apiUrlController.text = ApiService.apiUrl;
  }

  @override
  void dispose() {
    _phoneController.dispose();
    _nameController.dispose();
    _passwordController.dispose();
    _apiUrlController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_phoneController.text.trim().isEmpty || _passwordController.text.isEmpty) {
      _showError('Заполни телефон и пароль');
      return;
    }
    if (!_isLogin && _nameController.text.trim().isEmpty) {
      _showError('Введи имя');
      return;
    }
    if (!_isLogin && !_consent) {
      _showError('Необходимо согласие на обработку персональных данных');
      return;
    }
    setState(() => _isLoading = true);
    try {
      if (_isLogin) {
        await ApiService.login(_phoneController.text.trim(), _passwordController.text);
      } else {
        await ApiService.register(
          _phoneController.text.trim(),
          _nameController.text.trim(),
          _passwordController.text,
          consent: true,
        );
      }
      if (mounted) {
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(builder: (_) => const HomeScreen()),
        );
      }
    } catch (e) {
      _showError(e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _showError(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), backgroundColor: Colors.red.shade700),
    );
  }

  Future<void> _openPrivacyPolicy() async {
    final url = '${ApiService.apiUrl}/privacy';
    final uri = Uri.parse(url);
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;

    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 40),
              Icon(
                Icons.auto_stories_rounded,
                size: 72,
                color: cs.primary,
              ),
              const SizedBox(height: 16),
              Text(
                AppConfig.appName,
                textAlign: TextAlign.center,
                style: theme.textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: cs.onSurface,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Твой личный AI-дневник',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyLarge?.copyWith(
                  color: cs.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 40),

              // Toggle
              SegmentedButton<bool>(
                segments: const [
                  ButtonSegment(value: true, label: Text('Вход')),
                  ButtonSegment(value: false, label: Text('Регистрация')),
                ],
                selected: {_isLogin},
                onSelectionChanged: (s) => setState(() => _isLogin = s.first),
              ),
              const SizedBox(height: 24),

              if (!_isLogin) ...[
                TextField(
                  controller: _nameController,
                  decoration: const InputDecoration(
                    labelText: 'Имя',
                    prefixIcon: Icon(Icons.person_outline),
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 16),
              ],

              TextField(
                controller: _phoneController,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(
                  labelText: 'Телефон',
                  hintText: '+799****4567',
                  prefixIcon: Icon(Icons.phone_outlined),
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),

              TextField(
                controller: _passwordController,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: 'Пароль',
                  prefixIcon: Icon(Icons.lock_outline),
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),

              // Consent checkbox (only for registration)
              if (!_isLogin) ...[
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      width: 24,
                      height: 24,
                      child: Checkbox(
                        value: _consent,
                        onChanged: (v) => setState(() => _consent = v ?? false),
                        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: GestureDetector(
                        onTap: () => setState(() => _consent = !_consent),
                        child: RichText(
                          text: TextSpan(
                            style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant, height: 1.4),
                            children: [
                              const TextSpan(text: 'Я даю согласие на обработку '),
                              TextSpan(
                                text: 'персональных данных',
                                style: TextStyle(color: cs.primary, decoration: TextDecoration.underline),
                              ),
                              const TextSpan(
                                text: ', включая голосовые записи (биометрия), '
                                    'в соответствии с ',
                              ),
                              TextSpan(
                                text: 'политикой конфиденциальности',
                                style: TextStyle(color: cs.primary, decoration: TextDecoration.underline),
                                recognizer: null, // handled by tap on whole text
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    onPressed: _openPrivacyPolicy,
                    icon: const Icon(Icons.privacy_tip_outlined, size: 16),
                    label: const Text('Политика конфиденциальности', style: TextStyle(fontSize: 13)),
                    style: TextButton.styleFrom(padding: const EdgeInsets.only(left: 32)),
                  ),
                ),
                const SizedBox(height: 8),
              ],

              FilledButton(
                onPressed: _isLoading ? null : _submit,
                child: _isLoading
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Text(_isLogin ? 'Войти' : 'Создать аккаунт'),
              ),
              const SizedBox(height: 16),

              // API URL setting
              OutlinedButton.icon(
                onPressed: () async {
                  final newUrl = await Navigator.push<String>(
                    context,
                    MaterialPageRoute(builder: (_) => SettingsScreen(isSetup: true)),
                  );
                  if (newUrl != null) {
                    setState(() => _apiUrlController.text = newUrl);
                  }
                },
                icon: const Icon(Icons.dns_outlined, size: 18),
                label: Text('Сервер: ${ApiService.apiUrl}'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
