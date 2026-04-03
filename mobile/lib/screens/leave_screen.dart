import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../services/api_models.dart';
import '../services/auth_store.dart';
import '../widgets/app_shell.dart';
import '../widgets/gsps_card.dart';

class LeaveScreen extends StatefulWidget {
  const LeaveScreen({super.key, required this.auth});
  final AuthStore auth;

  @override
  State<LeaveScreen> createState() => _LeaveScreenState();
}

class _LeaveScreenState extends State<LeaveScreen> {
  bool _busy = false;
  String? _error;
  List<LeaveTypeOut> _types = [];
  int? _selectedTypeId;
  DateTime? _start;
  DateTime? _end;
  final _reason = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadTypes();
  }

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  Future<void> _loadTypes() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final companyId = await widget.auth.getActiveCompanyId();
      if (companyId == null) throw Exception('Select company in Profile first');
      final api = ApiClient(widget.auth);
      final res = await api.dio.get('/leave/types', queryParameters: {'company_id': companyId});
      final arr = (res.data as List).cast<Map<String, dynamic>>();
      _types = arr.map(LeaveTypeOut.fromJson).toList();
      _selectedTypeId ??= _types.isNotEmpty ? _types.first.id : null;
    } on DioException catch (e) {
      _error = e.response?.data?.toString() ?? e.message;
    } catch (e) {
      _error = e.toString();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _pickDate({required bool isStart}) async {
    final initial = isStart ? (_start ?? DateTime.now()) : (_end ?? _start ?? DateTime.now());
    final d = await showDatePicker(
      context: context,
      firstDate: DateTime(DateTime.now().year - 1),
      lastDate: DateTime(DateTime.now().year + 2),
      initialDate: initial,
    );
    if (d == null) return;
    setState(() {
      if (isStart) {
        _start = d;
        if (_end != null && _end!.isBefore(d)) _end = d;
      } else {
        _end = d;
      }
    });
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final companyId = await widget.auth.getActiveCompanyId();
      if (companyId == null) throw Exception('Select company in Profile first');
      if (_selectedTypeId == null) throw Exception('No leave types configured');
      if (_start == null || _end == null) throw Exception('Select date range');

      final api = ApiClient(widget.auth);
      await api.dio.post(
        '/leave/requests',
        queryParameters: {'company_id': companyId},
        data: {
          'leave_type_id': _selectedTypeId,
          'start_date': _start!.toIso8601String().substring(0, 10),
          'end_date': _end!.toIso8601String().substring(0, 10),
          'reason': _reason.text.trim(),
        },
      );

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Leave request submitted')),
        );
      }
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
      title: 'Leave',
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (_busy) const LinearProgressIndicator(),
          if (_error != null)
            GspsCard(title: 'Error', subtitle: 'Fix the issue and try again.', child: Text(_error!)),
          GspsCard(
            title: 'Apply leave',
            subtitle: 'Choose leave type and date range.',
            child: Column(
              children: [
                DropdownButtonFormField<int>(
                  value: _selectedTypeId,
                  items: _types
                      .map(
                        (t) => DropdownMenuItem(value: t.id, child: Text(t.name)),
                      )
                      .toList(),
                  onChanged: _busy ? null : (v) => setState(() => _selectedTypeId = v),
                  decoration: const InputDecoration(labelText: 'Leave type'),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: _busy ? null : () => _pickDate(isStart: true),
                        icon: const Icon(Icons.calendar_month_outlined),
                        label: Text(
                          _start == null ? 'Start date' : _start!.toIso8601String().substring(0, 10),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: _busy ? null : () => _pickDate(isStart: false),
                        icon: const Icon(Icons.calendar_month_outlined),
                        label: Text(
                          _end == null ? 'End date' : _end!.toIso8601String().substring(0, 10),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _reason,
                  decoration: const InputDecoration(
                    labelText: 'Reason (optional)',
                    prefixIcon: Icon(Icons.notes_outlined),
                  ),
                  maxLines: 3,
                ),
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: _busy ? null : _submit,
                    icon: const Icon(Icons.send_rounded),
                    label: const Text('Submit leave request'),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

