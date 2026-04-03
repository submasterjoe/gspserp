import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../services/api_models.dart';
import '../services/auth_store.dart';
import '../widgets/app_shell.dart';
import '../widgets/gsps_card.dart';

class ScheduleScreen extends StatefulWidget {
  const ScheduleScreen({super.key, required this.auth});
  final AuthStore auth;

  @override
  State<ScheduleScreen> createState() => _ScheduleScreenState();
}

class _ScheduleScreenState extends State<ScheduleScreen> {
  bool _busy = false;
  String? _error;
  List<ScheduleItemOut> _items = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final companyId = await widget.auth.getActiveCompanyId();
      if (companyId == null) throw Exception('Select company in Profile first');
      final api = ApiClient(widget.auth);
      final res = await api.dio.get('/schedule', queryParameters: {'company_id': companyId});
      final arr = (res.data as List).cast<Map<String, dynamic>>();
      _items = arr.map(ScheduleItemOut.fromJson).toList();
    } on DioException catch (e) {
      _error = e.response?.data?.toString() ?? e.message;
    } catch (e) {
      _error = e.toString();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      auth: widget.auth,
      title: 'Schedule',
      child: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (_busy) const LinearProgressIndicator(),
            if (_error != null)
              GspsCard(title: 'Error', subtitle: 'Pull down to retry.', child: Text(_error!)),
            for (final it in _items)
              GspsCard(
                title: it.title,
                subtitle: [
                  if (it.date != null) it.date!,
                  if (it.startTime != null && it.endTime != null) '${it.startTime}–${it.endTime}',
                ].join(' • '),
                trailing: _StatusChip(status: it.status),
                child: const SizedBox.shrink(),
              ),
            if (!_busy && _error == null && _items.isEmpty)
              const Padding(
                padding: EdgeInsets.all(24),
                child: Center(child: Text('No schedule items')),
              ),
          ],
        ),
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.status});
  final String status;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final isDone = status.toLowerCase() == 'done';
    final bg = isDone ? cs.primary.withValues(alpha: 0.12) : const Color(0xFFF1F5F9);
    final fg = isDone ? cs.primary : const Color(0xFF334155);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(borderRadius: BorderRadius.circular(999), color: bg),
      child: Text(
        status,
        style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: fg),
      ),
    );
  }
}

