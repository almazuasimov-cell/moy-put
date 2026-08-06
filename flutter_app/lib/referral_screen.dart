/// Экран реферальной программы «Мой путь»
/// Показывает код, заработанные дни Premium, поле ввода чужого кода и список приглашённых
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'api_service.dart';
import 'models.dart';

class ReferralScreen extends StatefulWidget {
  const ReferralScreen({super.key});

  @override
  State<ReferralScreen> createState() => _ReferralScreenState();
}

class _ReferralScreenState extends State<ReferralScreen> {
  ReferralInfo? _info;
  bool _isLoading = true;
  final _codeController = TextEditingController();
  String? _errorText;
  bool _isApplying = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _isLoading = true);
    try {
      _info = await ApiService.getReferralStats();
    } catch (_) {}
    if (mounted) setState(() => _isLoading = false);
  }

  Future<void> _applyCode() async {
    final code = _codeController.text.trim();
    if (code.isEmpty) {
      setState(() => _errorText = 'Введите код');
      return;
    }
    setState(() {
      _isApplying = true;
      _errorText = null;
    });
    try {
      final result = await ApiService.applyReferralCode(code);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(result['message'] ?? 'Код активирован!'),
            backgroundColor: Colors.green.shade700,
          ),
        );
        _codeController.clear();
        _load();
      }
    } catch (e) {
      if (mounted) {
        setState(() => _errorText = e.toString().replaceFirst('Exception: ', ''));
      }
    }
    if (mounted) setState(() => _isApplying = false);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Реферальная программа')),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: SingleChildScrollView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // ── Баланс ──────────────────────────
                    _balanceCard(cs, theme),
                    const SizedBox(height: 24),

                    // ── Мой код ────────────────────────
                    _myCodeCard(cs, theme),
                    const SizedBox(height: 24),

                    // ── Ввести чужой код ──────────────
                    _applyCodeCard(cs, theme),
                    const SizedBox(height: 24),

                    // ── Приглашённые друзья ────────────
                    if (_info != null && _info!.referrals.isNotEmpty) ...[
                      _invitedList(cs, theme),
                    ],
                  ],
                ),
              ),
            ),
    );
  }

  Widget _balanceCard(ColorScheme cs, ThemeData theme) {
    final days = _info?.premiumDaysEarned ?? 0;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            Icon(Icons.workspace_premium_rounded, size: 40, color: cs.primary),
            const SizedBox(height: 8),
            Text(
              'Заработано Premium',
              style: TextStyle(color: cs.onSurfaceVariant, fontSize: 14),
            ),
            const SizedBox(height: 4),
            Text(
              '$days ${_pluralDays(days)}',
              style: theme.textTheme.headlineMedium?.copyWith(
                fontWeight: FontWeight.bold,
                color: cs.primary,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              'Начисляется автоматически за приглашения',
              style: TextStyle(color: cs.onSurfaceVariant, fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }

  /// Русское склонение "день/дня/дней" — 1 день, 2-4 дня, 5+ дней
  /// (с исключением 11-14, которые всегда "дней").
  static String _pluralDays(int n) {
    final n100 = n % 100;
    if (n100 >= 11 && n100 <= 14) return 'дней';
    switch (n % 10) {
      case 1: return 'день';
      case 2:
      case 3:
      case 4: return 'дня';
      default: return 'дней';
    }
  }

  Widget _myCodeCard(ColorScheme cs, ThemeData theme) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Ваш реферальный код',
              style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 20),
              decoration: BoxDecoration(
                color: cs.primaryContainer.withOpacity(0.3),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: cs.primary.withOpacity(0.3)),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    _info?.code ?? '———',
                    style: theme.textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.bold,
                      letterSpacing: 3,
                      color: cs.primary,
                    ),
                  ),
                  const SizedBox(width: 12),
                  InkWell(
                    onTap: () {
                      Clipboard.setData(ClipboardData(text: _info?.code ?? ''));
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Код скопирован!')),
                      );
                    },
                    borderRadius: BorderRadius.circular(8),
                    child: Padding(
                      padding: const EdgeInsets.all(8),
                      child: Icon(Icons.copy_rounded, color: cs.primary, size: 22),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Text(
              'Поделитесь кодом с друзьями — и вы оба получите по 10 дней Premium!',
              style: TextStyle(color: cs.onSurfaceVariant, fontSize: 13),
            ),
          ],
        ),
      ),
    );
  }

  Widget _applyCodeCard(ColorScheme cs, ThemeData theme) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Ввести код друга',
              style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            Text(
              'Введите реферальный код друга и получите 10 дней Premium',
              style: TextStyle(color: cs.onSurfaceVariant, fontSize: 13),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _codeController,
              textCapitalization: TextCapitalization.characters,
              decoration: InputDecoration(
                hintText: 'Например: ALMAZ1A2B3C',
                errorText: _errorText,
                prefixIcon: const Icon(Icons.card_giftcard_rounded),
                suffixIcon: _isApplying
                    ? const Padding(
                        padding: EdgeInsets.all(12),
                        child: SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                      )
                    : IconButton(
                        icon: const Icon(Icons.arrow_forward_rounded),
                        onPressed: _applyCode,
                      ),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              ),
              onSubmitted: (_) => _applyCode(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _invitedList(ColorScheme cs, ThemeData theme) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Приглашённые друзья (${_info!.invitedCount})',
          style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 12),
        ..._info!.referrals.map((r) => Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                leading: CircleAvatar(
                  backgroundColor: cs.primaryContainer,
                  child: Icon(Icons.person_rounded, color: cs.primary),
                ),
                title: Text(r.name, style: TextStyle(color: cs.onSurface)),
                subtitle: Text(r.date, style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                trailing: Text(
                  '+${r.bonus} ${_pluralDays(r.bonus)}',
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    color: Colors.green.shade600,
                    fontSize: 16,
                  ),
                ),
              ),
            )),
      ],
    );
  }
}
